# Image du Space Hugging Face.
#
# Pourquoi un Dockerfile alors que l'application est une simple app Streamlit :
# Hugging Face a retiré `streamlit` de ses SDK intégrés. La création d'un Space
# n'accepte plus que « gradio », « docker » ou « static » — une tentative avec
# `space_sdk="streamlit"` est refusée par l'API :
#
#   Bad request: Invalid option: expected one of "gradio"|"docker"|"static" at sdk
#
# Les applications Streamlit passent donc par le SDK Docker, ce qui donne au
# passage la maîtrise de la version de Python et des dépendances.
#
# Contraintes de la plateforme (docs/hub/spaces-sdks-docker) :
#   - le conteneur tourne avec l'UID 1000 : on crée l'utilisateur et on fixe
#     WORKDIR **avant** tout COPY, et chaque COPY porte `--chown=user` ;
#   - le port exposé par défaut est 7860, déclaré par `app_port` dans le
#     README ; Streamlit écoute donc là plutôt que sur son 8501 habituel ;
#   - le disque n'est pas persistant : les ~253 Mo d'artefacts sont
#     retéléchargés depuis le dépôt de modèle à chaque démarrage à froid, dans
#     le cache de `huggingface_hub` sous $HOME.

FROM python:3.13-slim

# Utilisateur non privilégié, comme l'exige la plateforme.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# Les dépendances d'abord, le code ensuite : une modification de l'interface ne
# réinvalide pas la couche d'installation.
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY --chown=user . $HOME/app

EXPOSE 7860

# `--server.address=0.0.0.0` est indispensable : par défaut Streamlit n'écoute
# que sur la boucle locale et le Space répondrait « no application found ».
CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
