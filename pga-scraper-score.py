#!/usr/bin/env python3
import sys
import os
import time
import json
import re
import math

from xml.dom.minidom import getDOMImplementation, parseString

import redis

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = webdriver.Chrome()

r = redis.Redis(encoding='utf-8', decode_responses=True)
USE_REDIS = 'redis' in sys.argv
REDIS_TTL = 15 # in seconds

def leaderboard():
    """ scrape the leaderboard data from espn """
    driver.get('https://www.espn.com/golf/leaderboard')
    time.sleep(5)

    page_source = driver.page_source
    date_time_pattern = r'<!--.*?\|.*?\|.*?\|.*?\|.*?\| (.*?) -->'
    date_time_match = re.search(date_time_pattern, page_source, re.DOTALL)
    if date_time_match:
        date_time = date_time_match.group(1).strip()
        print("Timestamp:", date_time)
    else:
        date_time = 'unknown'
        print("No date and time found in the HTML comment.")
    pga_json = {'date_time': date_time}

    tables = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CLASS_NAME, 'Table__TBODY'))
    )

    for index, t in enumerate(tables):
        table = t.text
        tablelist = table.split('\n')

        json_output = []
        for i in range(0, len(tablelist), 3):
            record = { 'pos': tablelist[i].replace("-", "").replace(" ", ""), 'name': tablelist[i+1], 'cut': False }
            if (tablelist[i][:3] == 'The') or (tablelist[i][:3] == 'Pro'):
                break
            json_output.append(record)
        # process the cut
        if i < len(tablelist):
            start = i + 1
            for i in range(start, len(tablelist), 3):
                record = { 'pos': tablelist[i].replace("-", ""), 'name': tablelist[i+1], 'cut': True }
                json_output.append(record)
        pga_json['leaderboard'] = json_output
        if USE_REDIS:
            r.setex("pga-scaper-score:leaderboard", REDIS_TTL, json.dumps(pga_json))
        else:
            with open("leaderboard.json", "w", encoding='utf-8') as output_file:
                json.dump(pga_json, output_file, indent=4)

def load_leaderboard():
    """ loads the leaderboard data.  """
    if USE_REDIS:
        return json.loads(r.get("pga-scaper-score:leaderboard"))
    with open('leaderboard.json', encoding='utf-8') as file:
        return json.load(file)

def load_bets():
    """ Load bets from a JSON file """
    with open('bets.json', encoding='utf-8') as file:
        return json.load(file)

def calc_result():
    """
    Calculate the results of the bets based on the loaded leaderboard and bets. 
    Assign points to each bet and determine winnings for the top 3 scorers. 
    """
    leaderboard_json = load_leaderboard()

    name_to_pos = {entry["name"]: entry["pos"] for entry in leaderboard_json['leaderboard']}
    name_to_cut = {entry["name"]: entry["cut"] for entry in leaderboard_json['leaderboard']}

    bets_json = load_bets()
    bets_json['date_time'] = leaderboard_json['date_time']

    for person in bets_json['gamblers']:
        total = 0
        for bet in person["bet"]:
            pos = name_to_pos.get(bet['name'])
            if pos:
                bet["loc"] = pos.strip()
                pos = pos.replace(" ", "")
                pos = pos.replace("T", "")
                punten = 0
                if len(pos) > 0:   
                    if int(pos) < 10:
                        punten = 15
                        if int(pos) == int(bet['pos']):
                            punten = 30
                            if int(pos) == 1:
                                punten = 50
                bet["punten"] = punten
                total += punten

                bet['cut'] = name_to_cut.get(bet['name'])
            else:
                bet["loc"] = None
                if bet['name'] != "":
                    print(f"\tMissing: {bet['pos']}, Name: {bet['name']}")
        person["totaal"] = total

    bets_sorted = sorted(bets_json['gamblers'], key=lambda x: x["totaal"], reverse=True)
    bets_json['gamblers'] = bets_sorted

    for bet in bets_sorted:
        bet['winnings'] = ""

    total_prize = bets_json["pot"]
    prizes = [total_prize * 0.5, total_prize * 0.3, total_prize * 0.2]

    top_scores = sorted(set(player['totaal'] for player in bets_sorted), reverse=True)
    for i, score in enumerate(top_scores[:3]):
        bets_with_score = [p for p in bets_sorted if p['totaal'] == score]
        number_of_bets = len(bets_with_score)
        for bet in bets_with_score:
            winnings = "{:.2f}".format(math.floor(prizes[i] / number_of_bets *100) / 100)
            bet['winnings'] = '€ ' + winnings.replace(".", ",")

    if USE_REDIS:
        r.setex("pga-scaper-score:results", REDIS_TTL, json.dumps(bets_json))
    else:
        with open("results.json", "w", encoding='utf-8') as output_file:
            json.dump(bets_json, output_file, indent=4)

def load_result():
    """ Load the result data """
    if USE_REDIS:
        return json.loads(r.get("pga-scaper-score:results"))
    with open('results.json', encoding='utf-8') as file:
        return json.load(file)

def create_html():
    """
    Create an HTML document with various elements and data from the 'results_json' and 'load_leaderboard' functions, then write the result to a file named 'results.html'.
    """
    impl = getDOMImplementation()
    document_type = impl.createDocumentType(
        "html",
        "-//W3C//DTD XHTML 1.0 Strict//EN",
        "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd",
    )
    dom =  impl.createDocument("http://www.w3.org/1999/xhtml", "html", document_type)

    html = dom.documentElement
    head = html.appendChild(dom.createElement("head"))

    meta = dom.createElement('meta')
    meta.setAttribute('name', 'viewport')
    meta.setAttribute('content', 'width=device-width, initial-scale=1')
    head.appendChild(meta)

    meta = dom.createElement('meta')
    meta.setAttribute('charset', 'UTF-8')
    head.appendChild(meta)

    title = dom.createElement("title")
    title.appendChild(dom.createTextNode("Masters 2024"))
    head.appendChild(title)

    if os.path.exists('results.css'):
        css = dom.createElement("link")
        css.setAttribute('rel', 'stylesheet')
        css.setAttribute('href', 'results.css')
        head.appendChild(css)

    results_json = load_result()

    body = html.appendChild(dom.createElement("body"))
    div = dom.createElement("div")
    p = dom.createElement("p")
    p.setAttribute('class', 'timestamp')
    p.appendChild(dom.createTextNode(results_json['date_time']))
    div.appendChild(p)
    body.appendChild(div)

    # Ranking
    table = dom.createElement("table")
    table.setAttribute('class', 'leaders')

    thead = table.appendChild(dom.createElement("thead"))
    tr = dom.createElement("tr")
    th = dom.createElement("th")
    th.setAttribute('colspan', '3')
    th.setAttribute('class', 'ranking')
    th.appendChild(dom.createTextNode('Ranking'))
    tr.appendChild(th)
    thead.appendChild(tr)
    
    tbody = table.appendChild(dom.createElement("tbody"))
    for person in results_json['gamblers']:

        tr = dom.createElement("tr")

        td = dom.createElement("td")
        td.setAttribute('class', 'naam')
        td.appendChild(dom.createTextNode(person['name']))
        tr.appendChild(td)

        td = dom.createElement("td")
        td.setAttribute('class', 'score')
        td.appendChild(dom.createTextNode(str(person["totaal"])))
        tr.appendChild(td)

        td = dom.createElement("td")
        td.setAttribute('class', 'prijs')
        td.appendChild(dom.createTextNode(str(person["winnings"])))
        tr.appendChild(td)

        tbody.appendChild(tr)

    body.appendChild(table)

    # Gamblers
    table = dom.createElement("table")
    table.setAttribute('class', 'gokkers')

    for person in results_json['gamblers']:

        thead = dom.createElement("thead")
        tr = dom.createElement("tr")
        th = dom.createElement("th")
        th.setAttribute('colspan', '3')
        th.setAttribute('class', 'gokker')
        th.appendChild(dom.createTextNode(person['name']))
        tr.appendChild(th)
        thead.appendChild(tr)
        table.appendChild(thead)

        tbody = table.appendChild(dom.createElement("tbody"))
        for bet in person["bet"]:

            tr = dom.createElement("tr")

            td = dom.createElement("td")
            td.setAttribute('class', 'pos')
            td.appendChild(dom.createTextNode(bet['pos']))
            tr.appendChild(td)

            td = dom.createElement("td")
            clasr = 'golfer'
            if bet['cut']:
                clasr = clasr + ' cut'
            td.setAttribute('class', clasr)
            td.appendChild(dom.createTextNode(bet['name']))
            tr.appendChild(td)

            td = dom.createElement("td")
            td.setAttribute('class', 'punten')
            td.appendChild(dom.createTextNode(str(bet["punten"])))
            tr.appendChild(td)

            tbody.appendChild(tr)

        tr = dom.createElement("tr")

        td = dom.createElement("td")
        td.setAttribute('colspan', '2')
        td.setAttribute('class', 'totaal')
        td.appendChild(dom.createTextNode(""))
        tr.appendChild(td)

        td = dom.createElement("td")
        td.setAttribute('class', 'totaal punten')
        td.appendChild(dom.createTextNode(str(person["totaal"])))
        tr.appendChild(td)

        tbody.appendChild(tr)
        table.appendChild(tbody)

    body.appendChild(table)

    # Leaderboard
    table = dom.createElement("table")
    table.setAttribute('class', 'leaderboard')

    thead = table.appendChild(dom.createElement("thead"))
    tr = dom.createElement("tr")
    th = dom.createElement("th")
    th.setAttribute('colspan', '2')
    th.appendChild(dom.createTextNode('Leaderboard'))
    tr.appendChild(th)
    thead.appendChild(tr)
    
    tbody = table.appendChild(dom.createElement("tbody"))
    for person in load_leaderboard()['leaderboard']:

        tr = dom.createElement("tr")

        td = dom.createElement("td")
        td.setAttribute('class', 'position')
        td.appendChild(dom.createTextNode(str(person['pos'])))
        tr.appendChild(td)

        td = dom.createElement("td")
        td.setAttribute('class', 'naam')
        td.appendChild(dom.createTextNode(str(person["name"])))
        tr.appendChild(td)

        tbody.appendChild(tr)

    body.appendChild(table)

    script = dom.createElement("script")
    cdata = dom.createTextNode("""
function startAutoRefresh() {
    setInterval(function() {
        window.location.reload();
    }, 180000); 
}
startAutoRefresh();
""")
    script.appendChild(cdata)
    body.appendChild(script)

    xml_string = parseString(dom.toxml()).toprettyxml()

    if USE_REDIS:
        r.setex("pga-scaper-score:html", REDIS_TTL, xml_string)
    else:
        with open("results.html", "w", encoding="utf-8") as f:
            f.write(xml_string)

if __name__ == "__main__":
    leaderboard()
    calc_result()
    create_html()
