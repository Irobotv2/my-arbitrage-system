from flask import Flask, jsonify, render_template
import redis
import json

app = Flask(__name__)
redis_client = redis.Redis(host='localhost', port=6379, db=0)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    logs = []
    # Fetch the latest 50 logs from Redis
    log_entries = redis_client.lrange('arbitrage_paths', 0, 49)
    for entry in log_entries:
        log_data = json.loads(entry)
        logs.append(log_data)
    return jsonify(logs)

if __name__ == '__main__':
    app.run(debug=True)
