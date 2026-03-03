FROM python:3.11-slim

WORKDIR /app

RUN pip install litellm[proxy]

COPY litellm_config.yaml /app/litellm_config.yaml

EXPOSE 4000

CMD ["litellm", "--config", "litellm_config.yaml", "--port", "4000"]
