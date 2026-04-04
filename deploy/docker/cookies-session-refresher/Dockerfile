FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /session_refresher

ARG GECKODRIVER_VERSION=0.36.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       wget \
       gpg \
       tar \
       python3 \
       python3-venv \
       xvfb \
       dbus \
       dbus-x11 \
       at-spi2-core \
       fontconfig \
       libpci3 \
       libegl1 \
       util-linux \
    && install -d -m 0755 /etc/apt/keyrings \
    && wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- \
       | gpg --dearmor -o /etc/apt/keyrings/packages.mozilla.org.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.gpg] https://packages.mozilla.org/apt mozilla main" \
       > /etc/apt/sources.list.d/mozilla.list \
    && printf 'Package: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' \
       > /etc/apt/preferences.d/mozilla \
    && apt-get update \
    && apt-get install -y --no-install-recommends firefox \
    && wget -q "https://github.com/mozilla/geckodriver/releases/download/v${GECKODRIVER_VERSION}/geckodriver-v${GECKODRIVER_VERSION}-linux64.tar.gz" \
       -O /tmp/geckodriver.tar.gz \
    && tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin \
    && chmod +x /usr/local/bin/geckodriver \
    && rm -f /tmp/geckodriver.tar.gz \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && dbus-uuidgen > /etc/machine-id \
    && mkdir -p /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix \
    && if ! getent group 1000 >/dev/null; then groupadd --gid 1000 DJgurda; fi \
    && if ! getent passwd 1000 >/dev/null; then useradd --uid 1000 --gid 1000 --create-home --home-dir /home/DJgurda --shell /bin/bash DJgurda; fi \
    && mkdir -p /home/DJgurda/.cache \
    && chown -R 1000:1000 /home/DJgurda \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements-cookies.txt ./requirements.txt
RUN pip install --no-cache-dir -r ./requirements.txt

COPY src/session_refresher/refresh_session.py ./refresh_session.py
COPY src/session_refresher/refresh_session.sh ./refresh_session.sh

RUN chmod +x ./refresh_session.sh \
    && mkdir -p /session_refresher/firefox_profile

CMD ["bash", "./refresh_session.sh"]
