FROM mysterydemon/pypen:latest

# 构建期代理（由 docker compose build.args / --build-arg 注入）
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG http_proxy
ARG https_proxy
ARG ALL_PROXY
ARG NO_PROXY

WORKDIR /app
ARG S6_OVERLAY_VERSION=3.2.0.2
ARG S6_OVERLAY_ARCH=x86_64
# 用 curl 下载（会读取上方 HTTP(S)_PROXY 构建参数）；ADD 远程 URL 往往不走代理
RUN set -eux; \
    base="https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}"; \
    curl -fsSL --retry 5 --retry-all-errors --connect-timeout 30 \
      -o /tmp/s6-overlay-noarch.tar.xz \
      "${base}/s6-overlay-noarch.tar.xz"; \
    curl -fsSL --retry 5 --retry-all-errors --connect-timeout 30 \
      -o /tmp/s6-overlay-${S6_OVERLAY_ARCH}.tar.xz \
      "${base}/s6-overlay-${S6_OVERLAY_ARCH}.tar.xz"; \
    tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz; \
    tar -C / -Jxpf /tmp/s6-overlay-${S6_OVERLAY_ARCH}.tar.xz; \
    rm -f /tmp/s6-overlay-*.tar.xz
ENV PATH="/command:${PATH}"

COPY requirements.txt ./
RUN pip3 install --no-cache-dir uv
RUN uv pip install --system --no-cache -r requirements.txt
RUN mkdir -p /etc/s6/services /var/log/s6 /app/projects

COPY . .
EXPOSE 5000
CMD ["python3", "start.py"]
