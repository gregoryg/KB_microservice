# TODO: rewrite calls to model using functions API https://platform.openai.com/docs/api-reference/chat/create#chat/create-functions
# TODO: integrate this with Denote notes (notes directory)
# TODO: run denote file-renamer on newly-saved KB articles
# TODO: read PDF from URL
import os
import datetime
import uuid
from bs4 import BeautifulSoup
import requests
import logging
import json
import orgparse
import threading
import openai
from time import time, sleep

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# use these models that show good results
models = ['gpt-3.5-turbo', 'gpt-4', 'gpt-3.5-turbo-16k', 'gpt-4-32k']


###     file operations
def save_file(filepath, content):
    with open(filepath, 'w', encoding='utf-8') as outfile:
        outfile.write(content)

def open_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as infile:
        return infile.read()

def get_text_from_url(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    # Kill all script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    # Get text
    text = soup.get_text()

    # Break into lines and remove leading and trailing spaces on each line
    lines = (line.strip() for line in text.splitlines())

    # Break multi-headlines into a line each
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))

    # Drop blank lines
    text = '\n'.join(chunk for chunk in chunks if chunk)

    return text


###     chatbot functions



def chatbot(messages, model="gpt-4", temperature=0):
    openai.api_key = open_file('key_openai.txt').strip()
    max_retry = 4
    retry = 0
    while True:
        try:
            response = openai.ChatCompletion.create(model=model, messages=messages, temperature=temperature)
            text = response['choices'][0]['message']['content']
            # response, tokens, model
            return text, response['usage']['total_tokens'], model
        except Exception as oops:
            print(f'\n\nError communicating with OpenAI: "{oops}"')
            if 'maximum context length' in str(oops):
                a = messages.pop(1)
                print('\n\n DEBUG: Trimming oldest message')
                continue
            retry += 1
            if retry >= max_retry:
                print(f"\n\nExiting due to excessive errors in API: {oops}")
                exit(1)
            print(f'\n\nRetrying in {2 ** (retry - 1) * 5} seconds...')
            sleep(2 ** (retry - 1) * 5)

###     KB functions




def update_directory():
    kb_dir = 'kb/'
    directory = ''
    for filename in os.listdir(kb_dir):
        if filename.endswith('.org'):
            filepath = os.path.join(kb_dir, filename)
            kb = orgparse.load(filepath)
            directory += '\n%s - %s - %s - %s\n' % (filename, kb.get_file_property('title'), "<description>", ', '.join(kb.get_file_property_list('filetags')))
    save_file('directory.txt', directory.strip())



def search_kb(query):
    directory = open_file('directory.txt')
    system = open_file('system_search.txt').replace('<<DIRECTORY>>', directory)
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': query}]
    response, tokens, model = chatbot(messages)
    return json.loads(response)

# def create_article_url(url):
#     text = get_text_from_url(url)

def create_article(text='', url=''):
    # If url is specified, text value is ignored
    source = 'user'
    if url != '':
        source = url
        text = get_text_from_url(url)
    system = open_file('system_create.txt')
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': text}]
    response, tokens, model = chatbot(messages, model="gpt-4", temperature=0.5)  # response will be Org Mode document string
    extra_meta = '#+source: %s\n#+identifier: abcde\n#+created: [%s]\n#+model: %s\n#+setupfile: ~/projects/emacs/org-html-themes/org/theme-readtheorg-local.setup\n' % (source, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), model)
    save_file('kb/%s.org' % str(uuid.uuid4()), extra_meta + response)
    print('CREATE KB')
    # print('CREATE', kb['title'])



def update_article(payload):
    kb = open_yaml('kb/%s.yaml' % payload['title'])
    json_str = json.dumps(kb, indent=2)
    system = open_file('system_update.txt').replace('<<KB>>', json_str)
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': payload['input']}]
    response, tokens = chatbot(messages)  # response should be JSON string
    kb = json.loads(response)
    save_yaml('kb/%s.yaml' % kb['title'], kb)
    print('UPDATE', kb['title'])
