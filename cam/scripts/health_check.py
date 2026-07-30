#!/usr/bin/env python3
from flask import Flask, jsonify
import socket

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'hostname': socket.gethostname(),
        'service': 'camera-stream'
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=False)