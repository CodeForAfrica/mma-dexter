from sqlalchemy import (
    Column,
    Integer,
    String,
    Enum,
)

from sqlalchemy.orm import relationship

from ..app import db


class AnalysisNature(db.Model):
    """
    The type of analysis performed on a document.

    An analysis type determines what analysis fields in the database are
    used. There are three major types of analysis and each AnalysisNature
    must be linked to one of them:

    * anchor: the simplest analysis which the others are based on.
    * elections: election monitoring with a focus on fairness
    * children: children in the media, with a focus on the Children in the Media Principles

    Admins can define new analysis natures but they must be based on one of these.
    """
    __tablename__ = "analysis_natures"

    ELECTIONS = 'elections'
    CHILDREN  = 'children'
    ANCHOR    = 'anchor'
    ANCHOR_ID = 3

    ICONS = {
        ANCHOR: 'fa-dot-circle-o',
        ELECTIONS: 'fa-university',
        CHILDREN: 'fa-child',
    }

    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), nullable=False, index=True, unique=True)
    nature      = Column(Enum(ANCHOR, ELECTIONS, CHILDREN), nullable=False)

    # associations
    roles       = relationship("SourceRole", secondary="analysis_nature_source_roles", lazy=True, backref="analysis_natures", order_by="SourceRole.name")
    issues      = relationship("Issue", secondary="analysis_nature_issues", lazy=True, backref='analysis_natures')
    topics      = relationship("Topic", secondary="analysis_nature_topics", lazy=True, backref='analysis_natures')

    @property
    def form(self):
        from dexter.analysis.forms import AnchorAnalysisForm, ElectionsAnalysisForm, ChildrenAnalysisForm

        return {
            self.ANCHOR: AnchorAnalysisForm,
            self.ELECTIONS: ElectionsAnalysisForm,
            self.CHILDREN: ChildrenAnalysisForm,
        }[self.nature]

    def icon(self):
        return self.ICONS.get(self.nature)

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<AnalysisNature name='{}'>".format(self.name.encode('utf-8'))

    def __eq__(self, other):
        # when comparing with an int, compare based on id
        if isinstance(other, int):
            return self.id == other
        else:
            return NotImplemented

    def __ne__(self, other):
        # when comparing with an int, compare based on id
        if isinstance(other, int):
            return self.id != other
        else:
            return NotImplemented
    
    def __hash__(self):
        return hash(self.name)

    @classmethod
    def lookup(cls, name):
        return cls.query.filter(cls.name == name).first()

    @classmethod
    def create_defaults(cls):
        elections = AnalysisNature()
        elections.id = 1
        elections.name = cls.ELECTIONS
        elections.nature = cls.ELECTIONS

        children = AnalysisNature()
        children.id = 2
        children.name = cls.CHILDREN
        children.nature = cls.CHILDREN

        anchor = AnalysisNature()
        anchor.id = cls.ANCHOR_ID
        anchor.name = cls.ANCHOR
        anchor.nature = cls.ANCHOR

        return [elections, children, anchor]

    @classmethod
    def all(cls):
        return cls.query.order_by('name').all()


analysis_nature_issues = db.Table(
    'analysis_nature_issues',
    db.Column('analysis_nature_id', db.Integer(), db.ForeignKey('analysis_natures.id', ondelete='CASCADE')),
    db.Column('issue_id', db.Integer(), db.ForeignKey('issues.id', ondelete='CASCADE')))


analysis_nature_topics = db.Table(
    'analysis_nature_topics',
    db.Column('analysis_nature_id', db.Integer(), db.ForeignKey('analysis_natures.id', ondelete='CASCADE')),
    db.Column('topic_id', db.Integer(), db.ForeignKey('topics.id', ondelete='CASCADE')))


analysis_nature_source_roles = db.Table(
    'analysis_nature_source_roles',
    db.Column('analysis_nature_id', db.Integer(), db.ForeignKey('analysis_natures.id', ondelete='CASCADE')),
    db.Column('source_role_id', db.Integer(), db.ForeignKey('source_roles.id', ondelete='CASCADE')))
