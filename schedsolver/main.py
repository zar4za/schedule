import os
import json
import socket
import uuid
import time
import logging
from typing import Any, Dict, List, Tuple

import redis
from solver import generate_shift_schedule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RedisStreamClient:
    def __init__(
        self,
    ):
        # Load configuration from environment variables
        host = os.getenv('REDIS_HOST', 'redis')
        port = int(os.getenv('REDIS_PORT', 6379))
        db = int(os.getenv('REDIS_DB', 0))
        self.request_stream = os.getenv('REDIS_REQUEST_STREAM', 'schedule:requests')
        self.result_stream = os.getenv('REDIS_RESULT_STREAM', 'schedule:results')
        self.group = os.getenv('REDIS_CONSUMER_GROUP', 'scheduler_service')

        self.redis = redis.Redis(host=host, port=port, db=db)
        # Consumer name: hostname + random suffix
        self.consumer = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

        # Create consumer group if it doesn't exist
        try:
            self.redis.xgroup_create(self.request_stream, self.group, id='0', mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def read_requests(self, block_ms: int = 5000, count: int = 1) -> List[Tuple[bytes, Dict[bytes, bytes]]]:
        # Reads messages from the request stream
        resp = self.redis.xreadgroup(
            groupname=self.group,
            consumername=self.consumer,
            streams={self.request_stream: '>'},
            count=count,
            block=block_ms
        ) or []
        result = []
        for _, entries in resp:
            for message_id, fields in entries:
                result.append((message_id, fields))
        return result

    def ack_request(self, message_id: bytes) -> None:
        # Acknowledge processing of a message
        self.redis.xack(self.request_stream, self.group, message_id)

    def publish_result(self, result: Dict[str, Any]) -> None:
        # Publish result payload as JSON
        payload = json.dumps(result)
        self.redis.xadd(self.result_stream, {'payload': payload})


def process_request(payload: str) -> Dict[str, Any]:
    # Parse the JSON envelope
    request = json.loads(payload)
    logger.info(f"Processing request {request.get('request_id')}")

    start_time = time.perf_counter()
    schedule = generate_shift_schedule(
        doctors=request['doctors'],
        days=request['days'],
        shifts=request['shifts'],
        requirements=request['requirements'],
        availability=request['availability'],
        shift_durations=request['shift_durations'],
        max_weekly_hours=request['max_weekly_hours'],
        min_rest_hours=request.get('min_rest_hours', 11),
        preferences=request.get('preferences'),
        alpha=request.get('alpha', 1000),
        beta=request.get('beta', 5),
        gamma=request.get('gamma', 1),
    )
    solve_time = time.perf_counter() - start_time

    # Flatten schedule into assignments
    assignments = [
        {'staff_id': i, 'day': j, 'shift': k}
        for (i, j, k), val in schedule.items() if val
    ]

    return {
        'request_id': request.get('request_id'),
        'status': 'success',
        'assignments': assignments,
        'metrics': {
            'solve_time': solve_time,
            'num_assignments': len(assignments),
        }
    }


def main():
    # Initialize Redis client using environment configuration
    client = RedisStreamClient()
    logger.info("Scheduler service started, waiting for requests...")

    while True:
        try:
            messages = client.read_requests(
                block_ms=int(os.getenv('READ_BLOCK_MS', 5000)),
                count=int(os.getenv('READ_COUNT', 10))
            )
            if not messages:
                continue

            for msg_id, fields in messages:
                payload = fields.get(b'payload')
                if not payload:
                    client.ack_request(msg_id)
                    continue

                try:
                    result = process_request(payload.decode('utf-8'))
                    client.publish_result(result)
                except Exception as e:
                    logger.exception(f"Error processing request {msg_id}: {e}")
                    error_payload = json.loads(payload)
                    client.publish_result({
                        'request_id': error_payload.get('request_id'),
                        'status': 'error',
                        'error': str(e),
                    })
                finally:
                    client.ack_request(msg_id)

        except redis.exceptions.RedisError as e:
            logger.exception(f"Redis error: {e}")
            time.sleep(int(os.getenv('RECONNECT_DELAY', 5)))
        except KeyboardInterrupt:
            logger.info("Shutting down scheduler service.")
            break

if __name__ == '__main__':
    main()