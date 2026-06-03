FROM beaker-notebook

USER root

RUN adduser --home /home/user user
RUN adduser --home /home/beaker-agent beaker-agent
ENV BEAKER_AGENT_USER=beaker-agent
ENV BEAKER_SUBKERNEL_USER=user
ENV BEAKER_RUN_PATH=/opt/beaker
WORKDIR /home/user

CMD ["-m", "beaker_notebook.app.server_app"]
