import json
import logging
import os 
import pandas as pd
import numpy as np 
import json
from pathlib import Path

from harmony_config.productLines import PRODUCTLINES 

DATA_DIR = os.getenv("DATA_DIR")

# label: what the tensorflow model will spit out
# _id: tcg/deckdrafterprod unique _id
#   allows us to get more information about the card


# given a label (string), and a Game type
# return the _id (string) that is associated with that label
def label_to_id(label : str, g : PRODUCTLINES) -> str:
    if not isinstance(label, int):
        raise TypeError("[label_to_id] expected a [int] but got: ", label)
    if not isinstance(g, PRODUCTLINES):
        raise TypeError("[label_to_id] expected a [PRODUCTLINES] enum but got: ", g)

    json = label_to_json(label)

    # extract only the _id from the json object
    return ""

# given an _id (string), and a Game type
# return the label (string) that is associated with that _id
def id_to_label(_id : str, g : PRODUCTLINES) -> str:
    if not isinstance(_id, str):
        raise TypeError("[id_to_label] expected a [str] but got: ", _id)
    if not isinstance(g, PRODUCTLINES):
        raise TypeError("[id_to_label] expected a [PRODUCTLINES] enum but got: ", g)

    # look up the variable
    return ""

# given a label (string), and a Game type 
# return a json string with certain fields
def label_to_json(label : int, g : PRODUCTLINES) -> str:
    if not isinstance(label, int):
        raise TypeError("[label_to_json] expected a [int] but got: ", label)
    if not isinstance(g, PRODUCTLINES):
        raise TypeError("[label_to_json] expected a [PRODUCTLINES] enum but got: ", g)
         
    # master-labels.csv (for label -> _id)
    master_labels_path = Path(DATA_DIR, g.value, "master_labels.csv")
    master_labels = pd.read_csv(master_labels_path)

    predicted_id = master_labels[master_labels['label'] == label]['_id'].iloc[0]

    # deckdrafterprod.json (for _id -> various information)
    deckdrafterprod_path = Path(DATA_DIR, g.value, "deckdrafterprod.json")
    with open(deckdrafterprod_path, 'r') as deckdrafterprod_file:
        deckdrafterprod = json.load(deckdrafterprod_file)
    
    card_obj = {}
    for obj in deckdrafterprod:
        if str(obj['_id']) == str(predicted_id):
            logging.info('object with {_id} FOUND!')
            card_obj = obj
    if card_obj == {}:
        logging.warning(f'[label_to_json] object with {_id} not found... returning empty json object')

    # returns the raw object without any filtering of the fields 
    # each field name can be different based on the game, so we must process it
    return json.dumps(card_obj)


# given a json string (that is raw from the deckdrafterprod), and a Game type
# return a unified json string with the following information:
def format_json(json_string : str, g : PRODUCTLINES) -> str:
    if not isinstance(json_string, str):
        raise TypeError("[format_json] expected a json [str] but got: ", json_string)
    if not isinstance(g, PRODUCTLINES):
        raise TypeError("[format_json] expected a [PRODUCTLINES] enum but got: ", g)

    formatted_json_string = json.dumps({});
    data = json.loads(json_string)

    try: 
        if g == PRODUCTLINES.LORCANA:
            formatted_json_string = json.dumps({
                'name': data['productName'],
                '_id': data['_id'],
                'image_url': data['images']['large'],
                'tcgplayer_id': data['tcgplayer_productId'], 
                # TODO: this gives the first price that it finds in the listings
                # maybe take an average? or get the lowest one?
                'price': data['listings'][0]['price'],
                }, indent=4)
        # elif g == PRODUCTLINES.MTG:
        # elif g == PRODUCTLINES.POKEMON:
        else: raise ValueError()
    except KeyErro:
        logging.warning('[format_json] key not found... returning empty json object')
    except ValueError:
        logging.warning('Game Type' + g + 'not supported')
    finally:
        return formatted_json_string
