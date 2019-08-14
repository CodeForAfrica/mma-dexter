from unidecode import unidecode

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Float,
    func,
    Index,
    and_,
    or_,
    )
from sqlalchemy.orm import relationship

from ..app import db
from .with_offsets import WithOffsets

import re

punctuation_re = re.compile(r'[^0-9a-z]+$', re.IGNORECASE)

def sanitise_name(name):
    """
    Strip weird characters from names
    """
    name = punctuation_re.sub('', name)
    name = name.replace('\xa0', ' ')
    return name

class Entity(db.Model):
    """
    An entity (person, place etc.) mentioned or quoted in a document.

    Two instances are equal if they have the same name and group.
    """
    __tablename__ = "entities"

    id          = Column(Integer, primary_key=True)
    group       = Column(String(50), index=True, nullable=False)
    name        = Column(String(150), index=True, nullable=False)

    # entities with group == 'person' may have a linked person
    person_id   = Column(Integer, ForeignKey('people.id'))

    created_at   = Column(DateTime(timezone=True), index=True, unique=False, nullable=False, server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.current_timestamp())

    # Associations
    person      = relationship('Person', backref='entities', foreign_keys=[person_id], lazy=False)

    def json(self):
        return {
            'id': self.id,
            'name': self.name,
            'group': self.group,
        }

    def __eq__(self, other):
        # to compare, we emulate mysql's utf8_general_ci collation:
        # strip diacritics and lowercase
        return isinstance(other, Entity) and self.group.lower() == other.group.lower() \
            and unidecode(self.name).lower() == unidecode(other.name).lower()

    def __repr__(self):
        return "<Entity id={}, group=\"{}\", name=\"{}\">".format(self.id, self.group, self.name)

    def __hash__(self):
        # Since equality is based on name and group, hash must also be based on name and group
        return hash((self.name, self.group))

    def __str__(self):
        return self.name

    @classmethod
    def get_or_create(cls, group, name):
        """ Get the entity with this group and name or create it if it doesn't exist. """
        name = sanitise_name(name)

        e = Entity.query.filter(Entity.group == group[0:50], Entity.name == name[0:150]).first()
        if not e:
            e = Entity()
            e.group = group[0:50]
            e.name = name[0:150]
            db.session.add(e)
            # force a db write (within the transaction) so subsequent lookups
            # find this entity
            db.session.flush()
        return e

    @classmethod
    def bulk_get(self, pairs):
        """ For a collection of (group, name) pairs, fetch matching entities in
        bulk, returning a map from (group, name) pairs to the entity. Both
        group and name are lowercased in the resulting map. """
        entities = {}
        filters = [and_(Entity.group == p[0], Entity.name == p[1]) for p in pairs]
        for e in Entity.query.filter(or_(*filters)).all():
            entities[(e.group.lower(), e.name.lower())] = e
        return entities

Index('entity_group_name_ix', Entity.group, Entity.name, unique=True)


class DocumentEntity(db.Model, WithOffsets):
    """
    Entities referenced in a document.
    """
    __tablename__ = "document_entities"

    id        = Column(Integer, primary_key=True)
    doc_id    = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), index=True, nullable=False)
    entity_id = Column(Integer, ForeignKey('entities.id'), index=True)
    relevance = Column(Float, index=True, nullable=False)
    count     = Column(Integer, index=True, nullable=False, default=1)

    created_at   = Column(DateTime(timezone=True), index=True, unique=False, nullable=False, server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.current_timestamp())

    # offsets in the document, a space-separated list of offset:length pairs.
    offset_list  = Column(String(4096))

    # Associations
    entity    = relationship("Entity", lazy=False)


    def __repr__(self):
        return "<DocumentEntity doc={}, entity={}, relevance={}, count={}>".format(
                self.document, self.entity, self.relevance, self.count)

Index('doc_entity_doc_id_entity_id_ix', DocumentEntity.doc_id, DocumentEntity.entity_id, unique=True)
