# MLOps — traceability, versioning, continuous integration

This document describes how a result from this repository becomes reproducible,
and how a re-trained model is prevented from reaching production if it degrades
the service.

## 1. Why this was necessary

The project's first measurements were wrong: the models were trained on 100 % of
the data and then evaluated on that same data. ALS showed a HitRate@5 of
**0.2415**; with a correct temporal split it drops to **0.0415** — a factor of
**5.8** of imaginary accuracy, visible nowhere because nothing was traced. The
figure is reproducible: `python scripts/mesure_fuite.py`.

Three distinct gaps:

| Gap | Consequence |
|---|---|
| no train / validation / test split | metrics inflated by leakage |
| no record of the runs | you keep a number and lose the configuration |
| no quality gate | a degraded re-training publishes itself without warning |

## 2. Split and protocol

A **temporal** 60 / 20 / 20 split on `click_timestamp` (`src/evaluate.py`) — not
a random one: on a news stream, a random split lets the model learn from clicks
that came after the ones it is supposed to predict.

```
| 60 % training | 20 % validation | 20 % test |
t0 ----------- t60 ----------- t80 ------- tend
```

Three rules, established by notebooks 03 to 07:

1. **the candidate pool is recomputed at request time.** To evaluate on the test
   period, the history is `training + validation`. This is not leakage: a
   production service knows the past up to the present minute. A pool frozen at
   the end of training gives **0.0000** for every method;
2. **each method is tuned on the validation period**, and its settings are swept
   **jointly**. Comparing one tuned method against methods left at their
   defaults distorts the conclusion; so does juxtaposing partial optima — ALS
   ranges from 0.0110 to 0.0345 depending on the window × factors combination,
   and the combination obtained by taking the two winners of separate sweeps is
   the worst of the four (notebook 05, section 3);
3. **both collaborative models are re-trained on the history used for the
   measurement.** ALS was, SVD was not: it fell to 0.0005 instead of 0.0220,
   for want of data rather than any weakness of the model.

Tuning happens on validation; the test period is only used for the final
measurement.

## 3. Traceability (MLflow)

`src/tracking.py`. A **SQLite** backend (`mlflow.db`) rather than a directory of
files: MLflow 3 refuses the file store, and the model registry requires a
database.

```powershell
python -m src.evaluate --out-dir models_split --split val --skip-build --track
mlflow ui --backend-store-uri sqlite:///mlflow.db      # http://127.0.0.1:5000
```

Every run records:

- **parameters**: windows, factors, negatives, rating type, period sizes;
- **metrics**: HitRate@5, Recall@5, coverage, personalisation;
- **tags**: `git_commit` — so a number is tied to an exact state of the code.

MLflow is an **optional** dependency: if it is absent, tracking is skipped with
a warning, and a tracking failure never interrupts an evaluation.

## 4. Model versioning

The "model" in this project is a directory of `.npy` / `.pkl` artifacts, not a
serialised object. It is presented to the registry through a `pyfunc` wrapper:

```powershell
python -m src.evaluate --out-dir models_split --split test --skip-build `
    --register ricochet-artefacts
```

Each version keeps its metrics, its parameters and its commit, which makes a
rollback possible. The wrapper exists only for traceability: the production
service reads the artifacts directly, in numpy alone, and imports neither
MLflow, nor scikit-learn, nor Surprise.

## 5. Quality gate

`scripts/check_metrics.py` — this is the piece that separates an MLOps pipeline
from an automated training run.

```powershell
python -m src.evaluate --out-dir models_split --split test --skip-build --json metrics.json
python scripts/check_metrics.py --candidate metrics.json --tolerance 0.10
```

- compares `HitRate@5` and `Recall@5` against `models/baseline_metrics.json`;
- **exit code 1** if the drop exceeds the tolerance, so CI blocks the release;
- the other metrics are printed for information only;
- the reference is only updated deliberately (`--promote`) and it is **versioned
  in git**: without that it would follow the model's drift and would no longer
  protect anything.

Current reference: `popularity 1 h`, HitRate@5 = **0.2525**, Recall@5 = 0.0555
(test period, 2 000 readers). To regenerate it:

```bash
python -m src.evaluate --split test --skip-build --json models/baseline_metrics.json
```

Do not update it to make the gate pass: that is the gesture that empties it of
meaning. It is updated when the reference configuration changes, and the change
is stated.

## 6. Continuous integration

Two workflows, kept separate because they do not have the same needs.

### `.github/workflows/ci.yml` — on every push

Requires **no data** (the Globo dataset weighs 221 MB and is not versioned):

| Step | Checks |
|---|---|
| `pytest tests/` | the recommendation core, on synthetic artifacts — 87 tests |
| `sync_recommender.py --check` | the three deployed copies of the core are up to date |
| file sizes | no versioned file over 5 MB |
| artifacts | no `.npy` / `.pkl` / `.db` in git |
| `check_secrets.py` | no secret in clear text, **in any tracked file** |
| `terraform fmt -check` and `validate` | `infra/` is formatted and internally consistent |

#### The secret check, and why it was rewritten

The earlier version only looked for `AZURE_STORAGE_CONNECTION_STRING=` or
`HF_TOKEN=` assignments in `.py` and `.ipynb` files. It therefore let through
three forms this project actually handles:

- a connection string pasted as it is (`DefaultEndpointsProtocol=…`);
- a **function key inside a URL** (`?code=…`) — the form in which that key
  travels through every deployment command;
- either of those in a `.md` file, when the deployment commands live in the
  documentation.

`scripts/check_secrets.py` covers Azure connection strings and keys, SAS
signatures, function keys in URLs, Hugging Face and GitHub tokens, AWS
credentials and private keys. It **masks** whatever it finds: a build log is
public, and copying a leak out in full in order to report it would make matters
worse.

Two deliberate positions: no entropy-based detection (notebook image outputs are
base64 and would fire on every run, and a permanent alarm is an ignored alarm),
and explicitly tolerated placeholders (`$key`, `<KEY>`, `hf_...`) so that the
documentation stays writable. `tests/test_check_secrets.py` pins both sides —
28 cases, one of which checks that the real repository is clean.

**Before making the repository public**, the current state is not enough: a
removed secret is still readable in the history. Sweep every commit:

```bash
python scripts/check_secrets.py --history
```

#### The `pre-push` hook — the last moment it is still reversible

CI runs **after** the push: by then the secret is already at the host, and
erasing it means rewriting a published history. The hook, on the other hand,
refuses the push.

Choosing `pre-push` over `pre-commit` is deliberate: a local commit can be fixed
without consequence (`amend`, `rebase`, `reset`), and blocking every intermediate
work commit costs more than it protects. The push is the moment the content
becomes public and the history stops being yours alone.

One command, once per clone:

```bash
git config core.hooksPath scripts/hooks
```

`scripts/hooks/pre-push` is **versioned** — unlike `.git/hooks/`, which does not
follow the repository. Pointing `core.hooksPath` at it keeps it current without
any copying.

It does two things, in this order:

| Check | Scope | Why that scope |
|---|---|---|
| secrets | `--range <remote sha>..<local sha>` | only the commits being pushed. The whole history would be slow on every push, and the index would say nothing about commits already made |
| unit tests | `pytest tests/` | no data required, a few seconds |

Git supplies the pushed references on standard input, one line per reference —
the hook reads all of them, and handles a branch that is new on the remote (a
remote `sha` of zeroes) by comparing against what the remote already knows.

If a secret is found the stop is immediate: the tests do not run, and the message
is a reminder that the commit already exists locally, so the value has to be
revoked and the **local** history rewritten. For a false positive:
`git push --no-verify`.

The hook looks for the interpreter itself, preferring the project's own — that is
the one with `pytest`, and the virtual environment is not active inside a hook.
If it finds none, it lets the push through **while saying so**, rather than
blocking the work: CI will redo the checks.

Two details without which the hook would be useless:

- `.gitattributes` forces **LF** on `scripts/hooks/*`. With `core.autocrlf=true`
  (the default on Windows) the script would be checked out with CRLF, the
  interpreter would read `#!/bin/sh\r`, and the hook would not run — *with no
  error at push time*, so nobody would notice it had disappeared.
- The executable bit is recorded in the index (mode `100755`), so the hook also
  works on a Linux or macOS clone.

All three outcomes were verified: a clean range (the tests run, everything
green), a secret inside the pushed range (refused, tests not run), and a failing
test (refused).

#### Accepted findings (`.secretsignore`)

An earlier commit versioned the decoys of `tests/test_check_secrets.py` written
in clear text. They are assembled at runtime now, but the git history is still
readable: `--history` will always find them. Without an acceptance list, the
pre-publication check would be **permanently red**, and a real leak would be lost
among four known findings.

`.secretsignore` therefore lists those findings by **fingerprint** (a truncated
SHA-256 of the value, never the value) together with a justification. Three
deliberate properties:

- the file can be versioned without publishing anything;
- the fingerprint covers the exact value, so accepting a decoy does not accept a
  neighbouring secret — that is tested;
- the number of dismissed findings is **printed on every run**, so the list
  cannot grow in silence.

The history sweep reads every object in a single `git cat-file --batch`: 350 file
versions in 0.6 s. A first version spawned three git processes per file version
and took several minutes — enough to discourage running it at the moment it
matters.

### `.github/workflows/train.yml` — manual

```
data -> artifacts -> evaluation (MLflow) -> GATE -> publish to Blob / HF Hub
```

Publication is conditional on the gate. The data-retrieval step is left to be
completed according to the hosting (a self-hosted runner, or a download from a
storage account): the workflow fails on purpose rather than train on data that
is not there.

## 7. What is still missing

- **data retrieval in CI** — it blocks automatic re-training;
- **continuous recomputation of the window**: `popular_recent.npy` is produced
  today by the offline job, whereas the one-hour window is worth a factor of
  **42** in accuracy compared with the whole history
  (`models/freshness_sweep.json`);
- **a shared MLflow server** rather than a local SQLite file, as soon as a second
  person starts running experiments;
- **production monitoring**: the metrics measured here are offline. The real
  click-through rate on the recommendations remains the only judge.
