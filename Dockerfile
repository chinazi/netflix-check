ARG TARGETARCH
FROM python:3.11-alpine AS builder
ARG TARGETARCH
WORKDIR /build
RUN apk add --no-cache gcc musl-dev libffi-dev wget
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/build/deps -r requirements.txt

# 下载Clash - 根据架构使用不同版本
RUN echo "Downloading Clash for architecture: $TARGETARCH" && \
    if [ "$TARGETARCH" = "arm64" ]; then \
        MIHOMO_VERSION="v1.19.10"; \
        CLASH_URL="https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_VERSION}/mihomo-linux-arm64-${MIHOMO_VERSION}.gz"; \
        PLATFORM="linux/arm64"; \
    elif [ "$TARGETARCH" = "amd64" ]; then \
        MIHOMO_VERSION="v1.18.0"; \
        CLASH_URL="https://github.com/MetaCubeX/mihomo/releases/download/${MIHOMO_VERSION}/mihomo-linux-amd64-compatible-${MIHOMO_VERSION}.gz"; \
        PLATFORM="linux/amd64"; \
    else \
        echo "Unsupported architecture: $TARGETARCH" && exit 1; \
    fi && \
    wget -O mihomo.gz $CLASH_URL && \
    gunzip mihomo.gz && \
    chmod +x mihomo && \
    mv mihomo /build/clash && \
    echo "mihomo version: ${MIHOMO_VERSION}" > /build/version.txt && \
    echo "platform: ${PLATFORM}" >> /build/version.txt && \
    echo "download url: ${CLASH_URL}" >> /build/version.txt && \
    echo "build time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >> /build/version.txt && \
    echo "architecture: ${TARGETARCH}" >> /build/version.txt

FROM python:3.11-alpine
ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/deps
ENV CONFIG_FILE=/app/config/config.yaml

RUN apk add --no-cache \
    tzdata \
    ca-certificates \
    libstdc++ \
    gcompat \
    curl \
    jq \
    bash \
    net-tools \
    bind-tools

WORKDIR /app
COPY --from=builder /build/deps /app/deps
COPY --from=builder /build/clash /usr/local/bin/clash
COPY --from=builder /build/version.txt /app/version.txt
COPY app/ /app/app/

RUN mkdir -p /app/config /app/logs /app/temp /app/results \
    && mkdir -p /root/.config/mihomo

EXPOSE 8080

CMD ["python", "-u", "app/main.py"]