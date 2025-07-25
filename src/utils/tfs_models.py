import tomllib
import logging
import os
import requests

import numpy as np

from utils.product_lines import PRODUCTLINES as PLS
from utils.singleton import Singleton
from utils.file_handler.pickle import load_ids

# TODO : move to api package?
# but keep some of the features

# TODO : move to api package?
# but keep some of the features

def identify(instances: list, model_name: str, pl: PLS) -> tuple[list[str], list[float]]:
    '''
    Identifies a card with multiple models, giving the most confident output.

    Args:
        instances (list): The list of preprocessed images that are converted to a tensor, which is converted to a list
        model_name (string): unique identifier for which (sub)model we are using for evaluation
            ex) in the model "m12.keras", the model_name is "m12"
            ex) in the labels toml "m0_labels.toml", the model_name is "m0"
        pl (PRODUCTLINES): The product_line we are working with.

    Returns:
        tuple[list[str | None], list[float]]: a tuple containing:
            - list of most confident labels (or None if there is some sort of error)
            - list of confidences corresponding to each label
    '''

    TFS_PORT = os.getenv('TFS_PORT')
    url = f'http://tfs-{pl.value}:{TFS_PORT}/v1/models/{model_name}:predict'

    try:
        response = requests.post(url, json={'instances': instances}, timeout=10)
        response.raise_for_status()
        predictions = response.json().get('predictions', [])
    except Exception as e:
        logging.warning('Model [%s] failed to get predictions: %s', model_name, str(e))
        return [None] * len(instances), [0.0] * len(instances)

    final_prediction_labels = [None] * len(instances)
    confidences = [0.0] * len(instances)

    if CachedConfigs().request_config(pl)[model_name]['is_final']:
        for i, p in enumerate(predictions):
            try:
                p_np = np.array(p)
                best_idx = int(np.argmax(p_np))
                confidence = float(p_np[best_idx])
                final_prediction_labels[i] = best_idx
                confidences[i] = confidence
                logging.info('Model [%s] final prediction for image %d: %d (%.4f)', model_name, i, best_idx, confidence)
            except Exception as e:
                logging.warning('Model [%s] failed to process prediction for image %d: %s', model_name, i, str(e))
        return final_prediction_labels, confidences

    # Handle submodel routing
    submodel_inputs = {}
    image_indices_by_submodel = {}

    for i, p in enumerate(predictions):
        try:
            p_np = np.array(p)
            best_idx = int(np.argmax(p_np))
            confidence = float(p_np[best_idx])

            _ids: list[str] = load_ids(pl, model_name, 'rb') # TODO: move this outside of the for enumerate(predictions) loop

            next_model: str = _ids[best_idx]

            logging.info('Model [%s] defers image %d to submodel [%s] (label: %d)', model_name, i, next_model, best_idx)

            if next_model not in submodel_inputs:
                submodel_inputs[next_model] = []
                image_indices_by_submodel[next_model] = []

            submodel_inputs[next_model].append(instances[i])
            image_indices_by_submodel[next_model].append(i)
        except Exception as e:
            logging.warning('Model [%s] failed to defer image %d: %s', model_name, i, str(e))

    # Recurse into submodels
    for next_model, sub_instances in submodel_inputs.items():
        try:
            sub_labels, sub_confidences = identify(sub_instances, next_model, pl)
        except Exception as e:
            logging.warning('Submodel [%s] failed to identify batch: %s', next_model, str(e))
            sub_labels = [None] * len(sub_instances)
            sub_confidences = [0.0] * len(sub_instances)

        for idx, sub_label, sub_conf in zip(image_indices_by_submodel[next_model], sub_labels, sub_confidences):
            top_prediction = predictions[idx]
            top_conf = float(np.max(top_prediction))  # confidence of the top-level model
            final_prediction_labels[idx] = sub_label
            confidences[idx] = top_conf * sub_conf

    return final_prediction_labels, confidences


def get_model_metadata(model_name: str, pl: PLS) -> dict:
    '''
    gets the json dict of the metadata that tensorflow serving returns

    Args:
        model_name (string): unique identifier for which (sub)model we are using for evaluation
            ex) in the model "m12.keras", the model_name is "m12"
            ex) in the labels toml "m0_labels.toml", the model_name is "m0"
        pl (PRODUCTLINES): The product_line we are working with.
    Returns: 
        dict: json dict response from tfs metadata get request
    '''
    # port = get_port(pl) 
    port = os.getenv('TFS_PORT')
    url = f'http://tfs-{pl.value}:{port}/v1/models/{model_name}/metadata'
    return requests.get(url).json()


# TODO: pickled information may be easier?
def get_model_config(pl: PLS) -> dict:
    '''
    Gets the tensorflow model config.toml (shows the is_final status and no. of outputs a model has).
    
    Args:
        pl (PRODUCTLINES): The product_line we are working with.
    Returns:
        dict: the dictonary of the toml (in dictionary form)
    '''
    try:
        toml_path = 'config.toml'


        saved_model_dir = get_saved_model_dir()
        full_toml_path = os.path.join(saved_model_dir, pl.value, toml_path)

        with open(full_toml_path, 'rb') as f:
            return tomllib.load(f)

    except Exception as e:
        logging.error(' [get_model_config] unexpected error %s. Returning an empty dict.', e)
        return {}



# -------------------------------------------------------
class CachedConfigs(metaclass=Singleton):
    # TODO: pickled information may be easier?
    def __init__(self):
        self.cached_configs = {}
        for pl in PLS:
            self.cached_configs[pl.value] = get_model_config(pl)

            # for each of the product lines
            # find the one that is 'base'
            # that is the only one that needs height and width because all other models should be following the same format
            # this is for efficiency. why else should we be training the models off of different sized images?A
            # this might bite me in the butt when it comes to versioning... 
            metadata = get_model_metadata('m0', pl)
            input_width = int(metadata['metadata']['signature_def']['signature_def']['serve']['inputs']['input_layer']['tensor_shape']['dim'][1]['size'])
            input_height = int(metadata['metadata']['signature_def']['signature_def']['serve']['inputs']['input_layer']['tensor_shape']['dim'][2]['size'])

            self.cached_configs[pl.value]['m0']['input_width'] = input_width
            self.cached_configs[pl.value]['m0']['input_height'] = input_height 

    def request_config(self, pl: PLS) -> dict:
        try:
            return self.cached_configs[pl.value]
        except KeyError as e:
            logging.error(' [request_config] ps not loaded yet. Error: %s.', e)
            return {}

