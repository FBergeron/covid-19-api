import argparse
import collections
import json
import logging
import random
import shutil
import tempfile
import time
import urllib.parse
import urllib.request

import pandas as pd

from db_handler import DBHandler, Status
from log_handler import LogHandler
from meta_data_handler import MetaDataHandler
from twitter_handler import TwitterHandler
from util import load_config, COUNTRIES, ECOUNTRY_ICOUNTRIES_MAP

logger = logging.getLogger(__file__)
logging.basicConfig(level='DEBUG')

cfg = load_config()


def update_database(do_tweet: bool = False):
    db_handler = DBHandler(**cfg['db_handler'])
    log_handler = LogHandler(**cfg['log_handler'])

    logger.debug('Add automatically categorized pages.')
    data_path = cfg['data']['article_list']
    maybe_tweeted_ds = []
    with open(data_path, mode='r', encoding='utf-8') as f:
        for line in f:
            d = db_handler.upsert_page(json.loads(line))
            if d and do_tweet and d['status'] == Status.INSERTED and d['is_useful']:
                maybe_tweeted_ds.append(d)
    num_docs = db_handler.collection.count_documents({})
    log_handler.extend_page_number_log([f'{time.asctime()}:The number of pages is {num_docs}.'])

    logger.debug('Add manually checked pages.')
    for line in log_handler.iterate_topic_check_log():
        log = json.loads(line)
        existing_page = db_handler.collection.find_one({'page.url': log['url']})
        if not existing_page:
            continue
        db_handler.collection.update_one(
            {'page.url': log['url']},
            {'$set': {
                'page.is_about_COVID-19': log['is_about_COVID-19'],
                'page.is_useful': log['is_useful'],
                'page.is_about_false_rumor': log.get('is_about_false_rumor', 0),
                'page.is_checked': 1,
                'page.is_hidden': log.get('is_hidden', 0),
                'page.displayed_country': log['new_country'],
                'page.topics': {new_topic: 1.0 for new_topic in log['new_topics']}
            }}
        )

    logger.debug('Tweet a useful new page.')
    if do_tweet:
        twitter_handler = TwitterHandler(**cfg['twitter_handler'])
        if not maybe_tweeted_ds:
            logger.debug('No such pages. Skip to tweet a page.')
            return
        d = random.choice(maybe_tweeted_ds)
        text = twitter_handler.create_text(d)
        twitter_handler.post(text)


def update_stats():
    meta_data_handler = MetaDataHandler()
    log_handler = LogHandler(**cfg['log_handler'])

    logger.debug('Update stats.')
    base = 'https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data' \
           '/csse_covid_19_time_series/ '
    death_url = urllib.parse.urljoin(base, 'time_series_covid19_deaths_global.csv')
    confirmation_url = urllib.parse.urljoin(base, 'time_series_covid19_confirmed_global.csv')

    def fetch_data(url):
        with urllib.request.urlopen(url) as response:
            with tempfile.NamedTemporaryFile() as tmp_file:
                shutil.copyfileobj(response, tmp_file)
                return pd.read_csv(tmp_file.name)

    def get_last_update(df):
        return df.columns[-1]

    def get_stats(df, accessors):
        if 'all' in accessors:
            tmp_df = df.copy()
        else:
            tmp_df = df[df['Country/Region'].isin(accessors)]
        total = int(tmp_df.iloc[:, -1].sum())
        today = total - int(tmp_df.iloc[:, -2].sum())
        return total, today

    death_df = fetch_data(death_url)
    confirmation_df = fetch_data(confirmation_url)

    last_update = get_last_update(death_df)

    stats = {}
    for country in COUNTRIES:
        death_total, death_today = get_stats(death_df, country['dataRepository'])
        confirmation_total, confirmation_today = get_stats(confirmation_df, country['dataRepository'])
        stats[country['country']] = {
            'death_total': death_total,
            'confirmation_total': confirmation_total,
            'death_today': death_today,
            'confirmation_today': confirmation_today
        }

    meta_data_handler.set_stats({'last_updated': last_update, 'stats': stats})


def update_sources():
    meta_data_handler = MetaDataHandler()
    log_handler = LogHandler(**cfg['log_handler'])

    logger.debug('Update sources.')
    data_path = cfg['data']['site_list']
    with open(data_path) as f:
        d = json.load(f)

    sources = collections.defaultdict(list)
    for ecountry, icountries in ECOUNTRY_ICOUNTRIES_MAP.items():
        if ecountry == 'all':
            continue
        for domain, domain_info in d['domains'].items():
            if domain_info['region'] in icountries:
                for source in domain_info['sources']:
                    sources[ecountry].append(f'http://{source}')

    meta_data_handler.set_sources(sources)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--update_all', action='store_true', help='If true, update everything.')
    parser.add_argument('--update_database', action='store_true', help='If true, update the database.')
    parser.add_argument('--update_stats', action='store_true', help='If true, update the stats information.')
    parser.add_argument('--update_sources', action='store_true', help='If true, update the source information.')
    parser.add_argument('--do_tweet', action='store_true', help='If true, randomly tweet a newly registered page.')
    args = parser.parse_args()

    if args.update_all or args.update_database:
        update_database(do_tweet=args.do_tweet)

    if args.update_all or args.update_stats:
        update_stats()

    if args.update_all or args.update_sources:
        update_sources()


if __name__ == '__main__':
    main()
