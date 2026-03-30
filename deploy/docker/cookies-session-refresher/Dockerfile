FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /session_refresher

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       firefox-esr \
       xvfb \
       dbus-x11 \
       ca-certificates \
       procps \
       util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY src/session_refresher/refresh_session.sh ./refresh_session.sh
RUN chmod +x ./refresh_session.sh \
    && mkdir -p /session_refresher/firefox_profile

CMD ["bash", "./refresh_session.sh"]
