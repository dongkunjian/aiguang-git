# 爱逛GIT：FastAPI + SQLite，单容器即可跑（本地 / 云主机通用）
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 依赖先装，利用镜像层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite、头像缓存、每日备份都落在 /data —— 部署时把它挂成持久卷，数据就不会随容器重建而丢
ENV AIGUANG_DATA_DIR=/data
VOLUME /data

EXPOSE 8321

# server.py 优先读 PORT 环境变量（云平台会注入），否则用 8321
CMD ["python", "server.py"]
