import os
from redis import Redis
from rq import Worker, Queue, Connection

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

def main():
    redis_conn = Redis.from_url(REDIS_URL)
    with Connection(redis_conn):
        worker = Worker([Queue("default")])
        worker.work(with_scheduler=False)

if __name__ == "__main__":
    main()