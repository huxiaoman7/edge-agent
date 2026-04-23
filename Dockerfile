# 构建：docker build -t ascend310-agent .
# 运行：docker run -p 7860:7860 ascend310-agent
# 浏览器：http://localhost:7860
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py /app/
COPY src/ /app/src/
COPY data/ /app/data/
COPY web/ /app/web/
ENV HOST=0.0.0.0
ENV PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
