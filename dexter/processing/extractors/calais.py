import requests
import json

from .base import BaseExtractor
from ...models import DocumentEntity, Entity, Utterance, DocumentTaxonomy

import logging
log = logging.getLogger(__name__)


class CalaisExtractor(BaseExtractor):
    """ Use the OpenCalais API to extract entities and other
    useful goodies from a document.
    """
    API_KEY = None

    def __init__(self):
        pass

    def extract(self, doc):
        if doc.text:
            log.info("Extracting things for {}".format(doc))

            calais = self.fetch_data(doc)

            log.debug("Raw calais extractions: {}".format(calais))

            self.extract_entities(doc, calais)
            self.extract_utterances(doc, calais)
            self.extract_topics(doc, calais)

    def extract_entities(self, doc, calais):
        entities_added = 0

        for group, group_ents in list(calais.get('entities', {}).items()):
            group = self.normalise_name(group)

            for ent in list(group_ents.values()):
                if 'name' not in ent or len(ent['name']) < 2:
                    continue

                e = Entity.get_or_create(group, ent['name'])

                de = DocumentEntity()
                de.entity = e
                de.relevance = float(ent['relevance'])
                de.count = len(ent['instances'])
                for occurrence in ent['instances'][:100]:
                    de.add_offset((occurrence['offset'], occurrence['length']))

                if doc.add_entity(de):
                    entities_added += 1

        log.info("Added {} entities for {}".format(entities_added, doc))

    def extract_utterances(self, doc, calais):
        utterances_added = 0

        for quote in list(calais.get('relations', {}).get('Quotation', {}).values()):
            u = Utterance()
            u.quote = quote['quotation'].strip()

            if quote.get('instances', []):
                u.offset = quote['instances'][0]['offset']
                u.length = quote['instances'][0]['length']

            # uttering entity
            u.entity = Entity.get_or_create(
                self.normalise_name(quote['speaker']['_type']),
                quote['speaker']['name'])

            if doc.add_utterance(u):
                utterances_added += 1

        log.info("Added {} utterances for {}".format(utterances_added, doc))

    def extract_topics(self, doc, calais):
        added = 0

        for topicpairs in list(calais.get('topics', {}).values()):
            for topic in list(topicpairs.values()):
                dt = DocumentTaxonomy()
                dt.document = doc
                dt.label = topic['name'].replace('_', ' ')
                dt.score = topic['score']
                added += 1

        log.info("Added {} topics for {}".format(added, doc))

    def fetch_data(self, doc):
        if not doc.raw_calais:
            # fetch it
            # NOTE: set the ENV variable CALAIS_API_KEY before running the process
            if not self.API_KEY:
                raise ValueError('{}.{}.API_KEY must be defined.'.format(self.__module__, self.__class__.__name__))
            
            # File size limit
            if len(doc.text.encode('utf-8')) > 100000:
                return {}

            res = requests.post(
                'https://api.thomsonreuters.com/permid/calais',
                doc.text.encode('utf-8'),
                headers={
                    'x-ag-access-token': self.API_KEY,
                    'Content-Type': 'text/raw',
                    'outputFormat': 'application/json',
                })
            if res.status_code != 200:
                log.error(res.text)
                res.raise_for_status()

            res = res.json()
            doc.raw_calais = json.dumps(res)
        else:
            log.info("Using cached Calais data")
            res = json.loads(doc.raw_calais)

        # make the JSON decent and usable
        res = self.normalise(res)
        return res.get('extractions', {})

    def normalise(self, js):
        """ Change the JSON OpenCalais gives back into
        a nicer layout, keying extractions by their type.
        """
        # resolve references
        for key, val in list(js.items()):
            if isinstance(val, dict):
                for attr, attr_val in list(val.items()):
                    if isinstance(attr_val, str):
                        if attr_val in js:
                            val[attr] = js[attr_val]

        n = {}
        things = {}
        n['extractions'] = things

        # produces:
        #
        # extractions:
        #   entities:
        #     City: [ ... ]
        #     Person: [ ... ]
        #   relations:
        #     Quotation: [ ... ]

        for key, val in list(js.items()):
            grp = val.get('_typeGroup')

            if grp:
                if grp not in things:
                    things[grp] = {}
                grp = things[grp]

                typ = val.get('_type')
                if typ not in grp:
                    grp[typ] = {}

                grp[typ][key] = val
            else:
                n[key] = val

        return n
