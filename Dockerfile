FROM paddlepaddle/paddle:2.6.2

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Reduce thread-related crashes in containers
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1

# Keep your current safe flags (optional)
ENV FLAGS_use_mkldnn=0
ENV FLAGS_enable_pir_api=0
ENV FLAGS_use_new_executor=0

WORKDIR /app

COPY requirements.txt .

# IMPORTANT: remove paddlepaddle from requirements.txt (we already have it in base image)
RUN sed -i '/^paddlepaddle==/d' requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

COPY . .