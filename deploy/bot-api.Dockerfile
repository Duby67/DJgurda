# Official Telegram Bot API server pinned to an upstream commit; built in CI, never on the VM.
FROM alpine:3.22 AS builder
ARG BOT_API_COMMIT=e3e9dd8e5b3d7ab8537cd5a10dc31d5ffa8f82d1
RUN apk add --no-cache git cmake make g++ gperf linux-headers openssl-dev zlib-dev
WORKDIR /src
RUN git init -q . \
  && git remote add origin https://github.com/tdlib/telegram-bot-api.git \
  && git fetch -q --depth 1 origin "$BOT_API_COMMIT" \
  && git checkout -q FETCH_HEAD \
  && git submodule update -q --init --recursive --depth 1
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  && cmake --build build --target telegram-bot-api -j "$(nproc)" \
  && strip build/telegram-bot-api

FROM alpine:3.22 AS runtime
RUN apk add --no-cache libstdc++ openssl zlib
COPY --from=builder /src/build/telegram-bot-api /usr/local/bin/telegram-bot-api
# Same UID as the bot: it reads downloads from the shared volume, which this image may create.
RUN mkdir -p /data /var/lib/telegram-bot-api \
  && chown 10001:10001 /data /var/lib/telegram-bot-api
USER 10001:10001
ENTRYPOINT ["telegram-bot-api"]
