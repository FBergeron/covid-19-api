"""An API server for covid-19-ui."""
import json
import os

from flask import Flask, request, jsonify
from flask_cors import CORS

from util import load_config
from database import DBHandler

here = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)

cfg = load_config()
mongo = DBHandler(
    host=cfg['database']['host'],
    port=cfg['database']['port'],
    db_name=cfg['database']['db_name'],
    collection_name=cfg['database']['collection_name']
)


class InvalidUsage(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


@app.route('/')
def index():
    return "it works"


@app.route('/classes')
@app.route('/classes/<class_>')
@app.route('/classes/<class_>/<country>')
def classes(class_=None, country=None):
    start = request.args.get("start", "0")  # NOTE: set the default value as a `str` object
    limit = request.args.get("limit", "10")  # NOTE: set the default value as a `str` object
    if start.isdecimal() and limit.isdecimal():
        start = int(start)
        limit = int(limit)
    else:
        raise InvalidUsage('Parameters `start` and `limit` must be integers')
    filtered_pages = mongo.get_filtered_pages(topic=class_, country=country, start=start, limit=limit)
    return jsonify(filtered_pages)


@app.route('/meta')
def meta():
    with open(os.path.join(here, "data", "meta.json")) as f:
        meta_info = json.load(f)

    with open(os.path.join(here, "data", "stats.json")) as f:
        stats_info = json.load(f)

    country_code_index_map = {country["country"]: i for i, country in enumerate(meta_info["countries"])}
    for country_code, stats in stats_info["stats"].items():
        meta_info["countries"][country_code_index_map[country_code]]["stats"] = stats

    return jsonify(meta_info)


@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response
