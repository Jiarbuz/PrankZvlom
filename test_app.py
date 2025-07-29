from flask import Flask, request

app = Flask(__name__)

@app.route('/')
def index():
    return "Hello Flask!"

@app.route('/log', methods=['POST'])
def log():
    print("LOG RECEIVED")
    data = request.json
    return {"status": "ok", "data": data}

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
