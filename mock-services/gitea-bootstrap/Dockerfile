# Bootstrap image for Gitea provisioning.
#
# Built FROM the same Gitea image as the server so that:
#   - the `gitea` CLI is available (required to create the FIRST admin user,
#     which the REST API cannot do), and
#   - it can read the same /data volume/config as the server.
#
# This container is one-shot: it runs bootstrap.sh to completion and exits.
ARG GITEA_VERSION=1.27.3
FROM gitea/gitea:${GITEA_VERSION}

# bash + curl ship in the gitea image; jq is installed at runtime by the script
# (kept out of the image so we don't fight the gitea entrypoint/user model).
COPY bootstrap.sh /usr/local/bin/bootstrap.sh
RUN chmod +x /usr/local/bin/bootstrap.sh

# Override the gitea entrypoint so this container just runs our script.
ENTRYPOINT []
CMD ["/usr/local/bin/bootstrap.sh"]
