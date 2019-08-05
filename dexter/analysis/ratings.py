from collections import defaultdict

import xlsxwriter
from xlsxwriter.utility import xl_rowcol_to_cell, xl_col_to_name
from io import StringIO

from sqlalchemy.sql import func

from .utils import calculate_entropy
from ..models import *  # noqa


class ChildrenRatingExport:
    """ This class generates an XLSX export of per-media ratings
    based on stories analysed for the `children` analysis type.
    The produced spreadsheet contais both the final ratings
    and the raw data used to calculate the ratings. This means that
    users can dig into a rating to understand its context.
    The spreadsheet is also live, in that it contains live
    formulas so that a user can customise the ratings if
    required.

    The produced XLSX file has two worksheets:

    Rating: contains weighted per-media ratings across a number
            of different factors.
    Scores: the raw scores for each media used to calculate the
            overall rating.

    Ratings are weighted and can be composed of other ratings.
    For example, consider the rating

        0,500: Are Childrens Rights Respected
            0,100: Diversity of Roles
            0,200: Rights Respected
            0,700: Information Points
                0,500: Self-help
                0,500: Child's best interest

    In this case the "Are Childrens Rights Respected" rating
    has a weight of 0.500 and is composed of three sub-ratings,
    each with their own weights. The last rating, "Information Points",
    is in turn made up of weighted sub-ratings.

    A score for each rating is calculated based on the content and
    analysis of all the documents for a medium.
    """

    ratings = [[1.0, 'Final rating', [
        [0.500, 'Are Childrens Rights Respected', [
            [0.123, 'Diversity of Roles'],
            [0.326, 'Percent Rights respected'],
            [0.369, 'Access Codes', [
                [0.833, 'Percent Abused sources'],
                [0.167, 'Percent Non-abused sources']]],
            [0.181, 'Information Points', [
                [0.500, 'Percent Self Help'],
                [0.500, 'Percent S. Child\'s best interest']]]]],

        [0.249, 'Are Childrens Voices Heard?', [
            [0.083, 'Quoted Gender Ratio'],
            [0.418, 'Percent Quoted child sources'],
            [0.091, 'Diversity of Quoted Origins'],
            [0.178, 'No of Children Sources', [
                [0.067, 'Percent 1 Child Sources'],
                [0.133, 'Percent 2 Child Sources'],
                [0.200, 'Percent 3 Child Sources'],
                [0.267, 'Percent 4 Child Sources'],
                [0.333, 'Percent >4 Child Sources']]],
            [0.230, 'Percent Child sources']]],

        [0.125, 'Are Childrens Issued covered in Depth', [
            [0.053, 'Diversity of Topics'],
            [0.157, 'Percent Child Abuse'],
            [0.053, 'Diversity of Origins'],
            [0.105, 'Percent Focus origins'],
            [0.263, 'Information Points', [
                [0.084, 'Percent Basic Context'],
                [0.166, 'Percent Causes'],
                [0.166, 'Percent Consequences'],
                [0.166, 'Percent Solutions'],
                [0.166, 'Percent Policies'],
                [0.252, 'Percent Self Help']]],
            [0.263, 'Principles', [
                [0.200, 'Percent Rights respected'],
                [0.800, 'Inv. Percent Principles violated']]],
            [0.053, 'Sources', [
                [0.067, 'Percent 1 Sources'],
                [0.133, 'Percent 2 Sources'],
                [0.200, 'Percent 3 Sources'],
                [0.267, 'Percent 4 Sources'],
                [0.333, 'Percent >4 Sources']]],
            [0.053, 'Percent Focus types'],
        ]],

        [0.125, 'Is there Diversity in the Media', [
            [0.318, 'Roles', [
                [0.500, 'Percent Positive Roles'],
                [0.50, 'Percent Negative Roles']]],
            [0.134, 'Diversity of Roles'],
            [0.295, 'Sex', [
                [0.157, 'Diversity of Gender'],
                [0.249, 'Gender Ratio'],
                [0.594, 'Role', [
                    [0.667, 'Gender score Positive Roles'],
                    [0.333, 'Gender score Negative Roles']]]]],
            [0.126, 'Diversity of Ages'],
            [0.126, 'Diversity of Races']]],
    ]]]

    def __init__(self, doc_ids):
        # we use these to filter our queries, rather than trying to pull
        # complex filter logic into our view queries
        self.doc_ids = doc_ids
        self.formats = {}

        # map from a score name to its row in the score sheet
        self.score_row = {}
        self.n_columns = 0

        # collect media headings
        medium_ids = self.filter(db.session.query(func.distinct(Document.medium_id)))
        self.media = Medium.query\
            .filter(Medium.id.in_(medium_ids))\
            .order_by(Medium.name)\
            .all()

        self.n_columns = len(self.media)
        self.score_col_start = 3

        # how nested are the ratings?
        def depth(ratings, deep=1):
            for rating in ratings:
                if len(rating) < 3:
                    yield deep
                else:
                    yield max(depth(rating[2], deep + 1))

        # the column at which the ratings for each medium starts
        self.rating_col_start = (max(depth(self.ratings)) - 1) * 2

    def build(self):
        """
        Generate an Excel spreadsheet and return it as a string.
        """
        output = StringIO

        workbook = xlsxwriter.Workbook(output)

        self.formats['date'] = workbook.add_format({'num_format': 'yyyy/mm/dd'})
        self.formats['bold'] = workbook.add_format({'bold': True})

        # generate the sheets we'll use
        self.rating_ws = workbook.add_worksheet('Rating')
        self.scores_ws = workbook.add_worksheet('Raw')

        self.build_scores_worksheet()
        self.build_rating_worksheet()

        workbook.close()
        output.seek(0)

        return output.read()

    def build_scores_worksheet(self):
        """ Build up the scores worksheet. """
        for i, medium in enumerate(self.media):
            self.scores_ws.write(1, self.score_col(i), medium.name)

        row = 4
        row = self.totals(row) + 2
        row = self.source_totals(row) + 2
        row = self.race_scores(row) + 2
        row = self.age_scores(row) + 2
        row = self.quality_scores(row) + 2
        row = self.child_source_scores(row) + 2
        row = self.roles_scores(row) + 2
        row = self.victim_scores(row) + 2
        row = self.principle_scores(row) + 2
        row = self.child_gender_scores(row) + 2
        row = self.origin_scores(row) + 2
        row = self.topic_scores(row) + 2
        row = self.type_scores(row) + 2

    def totals(self, row):
        """ Counts of articles and sources """
        self.scores_ws.write(row, 0, 'Articles')
        rows = self.filter(
            db.session.query(
                Medium.name,
                func.count(1).label('freq'))
            .join(Document)
            .group_by(Medium.name)
        ).all()
        self.write_simple_score_row('Total articles', rows, row)

        row += 2

        self.scores_ws.write(row, 0, 'Sources')
        rows = self.filter(
            db.session.query(
                Medium.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(DocumentSource)
            .group_by(Medium.name)
        ).all()
        self.write_simple_score_row('Total sources', rows, row)

        return row

    def source_totals(self, row):
        # source counts per document
        rows = self.source_counts(children=False, limit=4)
        rows = [[m, c + ' Sources', v] for m, c, v in rows]
        buckets = ['1 Sources', '2 Sources', '3 Sources', '4 Sources', '>4 Sources']
        starting_row = row
        row = self.write_score_table(buckets, rows, row) + 1
        row = self.write_percent_table(buckets, self.score_row['Total articles'], starting_row, row)

        return row

    def child_gender_scores(self, row):
        """ Counts of genders of child sources """
        from dexter.models.views import DocumentSourcesView

        # QUOTED child genders
        self.scores_ws.write(row, 0, 'Quoted Child Genders')

        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentSourcesView.c.gender,
                func.count(1).label('freq'))
            .select_from(DocumentSourcesView)
            .join(Document, DocumentSourcesView.c.document_id == Document.id)
            .join(Medium)
            .filter(DocumentSourcesView.c.source_type == 'child')
            .filter(DocumentSourcesView.c.quoted == 'quoted')
            .group_by(Medium.name, DocumentSourcesView.c.gender)
            .order_by(Medium.name)
        ).all()

        rows = [[m, g or 'Unknown', c] for m, g, c in rows]
        genders = set(r[1] for r in rows)
        genders.update(['Male', 'Female'])
        genders = list(genders)
        genders.sort()

        row = self.write_score_table(genders, rows, row) + 1

        # male / female ratio
        male, female = self.score_row['Male'], self.score_row['Female']
        formula = '=IF({{col}}{}>0,{{col}}{}/{{col}}{},0)'.format(male + 1, female + 1, male + 1)
        self.write_formula_score_row('Quoted Boys to girls', formula, row)
        row = row + 1
        formula = '=IF({{col}}{}>1,1/{{col}}{},{{col}}{})'.format(row, row, row)
        self.write_formula_score_row('Quoted Gender Ratio', formula, row)
        row = row + 2

        # ALL child genders
        self.scores_ws.write(row, 0, 'All Child Genders')

        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentSourcesView.c.gender,
                func.count(1).label('freq'))
            .select_from(DocumentSourcesView)
            .join(Document, DocumentSourcesView.c.document_id == Document.id)
            .join(Medium)
            .filter(DocumentSourcesView.c.source_type == 'child')
            .group_by(Medium.name, DocumentSourcesView.c.gender)
            .order_by(Medium.name)
        ).all()

        rows = [[m, g or 'Unknown', c] for m, g, c in rows]
        genders = set(r[1] for r in rows)
        genders.update(['Male', 'Female'])
        genders = list(genders)
        genders.sort()

        row = self.write_score_table(genders, rows, row) + 1

        # male / female ratio
        male, female = self.score_row['Male'], self.score_row['Female']
        formula = '=IF({{col}}{}>0,{{col}}{}/{{col}}{},0)'.format(male + 1, female + 1, male + 1)
        self.write_formula_score_row('Boys to girls', formula, row)
        row = row + 1
        formula = '=IF({{col}}{}>1,1/{{col}}{},{{col}}{})'.format(row, row, row)
        self.write_formula_score_row('Gender Ratio', formula, row)
        row = row + 1

        # male / female entropy
        rows = [r for r in rows if r[1] in ['Male', 'Female']]
        self.write_simple_score_row('Diversity of Gender', self.entropy(rows), row)

        return row

    def child_source_scores(self, row):
        """ Counts of children sources, how many speak, etc. """
        self.scores_ws.write(row, 0, 'Child Sources')

        # all child sources
        rows = self.filter(
            db.session.query(
                Medium.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(DocumentSource)
            .filter(DocumentSource.source_type == 'child')
            .group_by(Medium.name)
        ).all()
        self.write_simple_score_row('Total child sources', rows, row)
        row += 1
        self.write_percent_row('Child sources', self.score_row['Total sources'], row - 1, row)
        row += 1

        # quoted child sources
        rows = self.filter(
            db.session.query(
                Medium.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(DocumentSource)
            .filter(DocumentSource.source_type == 'child')
            .filter(DocumentSource.quoted == True)
            .group_by(Medium.name)
        ).all()  # noqa
        self.write_simple_score_row('Quoted child sources', rows, row)
        row += 1

        # percent of all sources
        self.write_percent_row('Quoted child sources', self.score_row['Total sources'], row - 1, row)
        row += 1

        # source counts per document
        rows = self.source_counts(children=True, limit=4)
        rows = [[m, c + ' Child Sources', v] for m, c, v in rows]
        buckets = ['1 Child Sources', '2 Child Sources', '3 Child Sources', '4 Child Sources', '>4 Child Sources']

        starting_row = row
        row = self.write_score_table(buckets, rows, row) + 1
        row = self.write_percent_table(buckets, self.score_row['Total articles'], starting_row, row) + 1

        # origin of documents with quoted children
        self.scores_ws.write(row, 0, 'Origins of Quoted Children')
        rows = self.filter(
            db.session.query(
                Medium.name,
                Location.name,
                func.count(func.distinct(Document.id)).label('freq'))
            .join(Document)
            .join(DocumentSource)
            .join(Location)
            .filter(DocumentSource.source_type == 'child')
            .filter(DocumentSource.quoted == True)
            .group_by(Medium.name)  # noqa
        ).all()
        origins = list(set(r[1] for r in rows))
        row = self.write_score_table(origins, rows, row)
        # entropy
        self.write_simple_score_row('Diversity of Quoted Origins', self.entropy(rows), row)
        row += 1

        return row

    def roles_scores(self, row):
        """ Counts of source roles per medium, and their entropy. """
        self.scores_ws.write(row, 0, 'Child Roles')

        rows = self.filter(
            db.session.query(
                Medium.name,
                SourceRole.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(DocumentSource)
            .join(SourceRole)
            .filter(DocumentSource.source_type == 'child')
            .group_by(Medium.name, SourceRole.name)
            .order_by(Medium.name)
        ).all()

        roles = list(set(r[1] for r in rows))
        roles.sort()

        row = self.write_score_table(roles, rows, row) + 1
        self.write_simple_score_row('Diversity of Roles', self.entropy(rows), row)

        # positive and negative roles
        for indication in ['positive', 'negative']:
            row += 2
            roles = db.session.query(SourceRole).filter(SourceRole.indication == indication).all()
            roles = sorted([r.name for r in roles])

            title = indication.capitalize() + ' Roles'
            self.scores_ws.write(row, 0, title)

            rows = self.filter(
                db.session.query(
                    Medium.name,
                    SourceRole.name,
                    func.count(1).label('freq'))
                .join(Document)
                .join(DocumentSource)
                .join(SourceRole)
                .filter(SourceRole.indication == indication)
                .filter(DocumentSource.source_type == 'child')
                .group_by(Medium.name, SourceRole.name)
            ).all()

            row = self.write_score_table(roles, rows, row) + 1
            formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(roles), row - 1)
            self.write_formula_score_row('Total ' + title, formula, row)
            row += 1
            # percent of all child sources
            self.write_percent_row(title, self.score_row['Total child sources'], row - 1, row)
            row += 2

            # male vs female
            score_rows = []
            for gender in ['Male', 'Female']:
                self.scores_ws.write(row, 0, gender + ' ' + title)

                rows = self.filter(
                    db.session.query(
                        Medium.name,
                        SourceRole.name,
                        func.count(1).label('freq'))
                    .join(Document)
                    .join(DocumentSource)
                    .join(SourceRole)
                    .join(Gender)
                    .filter(SourceRole.indication == indication)
                    .filter(DocumentSource.source_type == 'child')
                    .filter(Gender.name == gender)
                    .group_by(Medium.name, SourceRole.name)
                ).all()

                row = self.write_score_table(roles, rows, row) + 1
                formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(roles), row - 1)
                self.write_formula_score_row('Total {} {}'.format(gender, title), formula, row)
                score_rows.append(row)
                row += 2

            # now do the ratio between the two
            male, female = score_rows
            formula = '=IF({{col}}{}>0,{{col}}{}/{{col}}{},0)'.format(male + 1, female + 1, male + 1)
            self.write_formula_score_row('Gender ratio {}'.format(title, formula, row))
            row += 1
            formula = '=IF({{col}}{}>1,1/{{col}}{},{{col}}{})'.format(row, row, row)
            self.write_formula_score_row('Gender score {}'.format(title, formula, row))
            row += 1

        return row

    def age_scores(self, row):
        """ Counts of source ages per medium, and their entropy. """
        self.scores_ws.write(row, 0, 'Child Ages')

        rows = self.filter(
            db.session.query(
                Medium.name,
                SourceAge.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(DocumentSource)
            .join(SourceAge)
            .filter(DocumentSource.source_type == 'child')
            .group_by(Medium.name, SourceAge.name)
            .order_by(Medium.name)
        ).all()

        ages = list(set(r[1] for r in rows))
        ages.sort()

        row = self.write_score_table(ages, rows, row) + 1
        self.write_simple_score_row('Diversity of Ages', self.entropy(rows), row)

        return row

    def race_scores(self, row):
        """ Counts of source races per medium, and their entropy. """
        self.scores_ws.write(row, 0, 'Races')

        rows = self.filter(
            db.session.query(
                Medium.name,
                Race.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(DocumentSource)
            .join(Race)
            .filter(DocumentSource.source_type == 'child')
            .group_by(Medium.name, Race.name)
            .order_by(Medium.name)
        ).all()

        races = list(set(r[1] for r in rows))
        races.sort()

        row = self.write_score_table(races, rows, row) + 1
        self.write_simple_score_row('Diversity of Races', self.entropy(rows), row)

        return row

    def topic_scores(self, row):
        """ Counts of document topics per medium, and their entropy. """
        self.scores_ws.write(row, 0, 'Topics')

        rows = self.filter(
            db.session.query(
                Medium.name,
                Topic.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(Topic)
            .group_by(Medium.name, Topic.name)
        ).all()
        roles = list(set(r[1] for r in rows))
        roles.sort()

        row = self.write_score_table(roles, rows, row) + 1
        self.write_simple_score_row('Diversity of Topics', self.entropy(rows), row)
        row += 1

        # 2. Child Abuse
        rows = self.filter(
            db.session.query(
                Medium.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(Topic)
            .filter(Topic.group == '2. Child Abuse')
            .group_by(Medium.name, Topic.name)
        ).all()

        self.write_simple_score_row('Child Abuse', rows, row)
        row += 1
        self.write_percent_row('Child Abuse', self.score_row['Total articles'], row - 1, row)

        return row

    def type_scores(self, row):
        """ Counts of document types per medium """
        self.scores_ws.write(row, 0, 'Types')

        # feature these types
        types = ['News story', 'Editorial', 'Opinion piece', 'Feature/news analysis', 'Business', 'Sport']
        types.sort()

        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentType.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(DocumentType)
            .filter(DocumentType.name.in_(types))
            .group_by(Medium.name, DocumentType.name)
        ).all()

        row = self.write_score_table(types, rows, row) + 1

        formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(types), row - 1)
        self.write_formula_score_row('Focus types', formula, row)
        row += 1
        self.write_percent_row('Focus types', self.score_row['Total articles'], row - 1, row)

        return row

    def origin_scores(self, row):
        """ Counts of document origins per medium, and their entropy. """
        self.scores_ws.write(row, 0, 'Origins')

        rows = self.filter(
            db.session.query(
                Medium.name,
                Location.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(Location)
            .group_by(Medium.name, Location.name)
        ).all()
        origins = list(set(r[1] for r in rows))
        origins.sort()

        row = self.write_score_table(origins, rows, row) + 1
        self.write_simple_score_row('Diversity of Origins', self.entropy(rows), row)

        # focus origins
        row += 2
        self.scores_ws.write(row, 0, 'Focus origins')
        origins = ['Eastern Cape', 'Limpopo', 'Free State', 'Mpumalanga', 'North West', 'Northern Cape']
        row = self.write_score_table(origins, rows, row) + 1

        starting_row = row
        formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(origins), row - 1)
        self.write_formula_score_row('Focus origins', formula, row)
        row += 1
        self.write_percent_row('Focus origins', self.score_row['Total articles'], starting_row, row)

        return row

    def entropy(self, rows):
        data = defaultdict(dict)
        for medium, label, count in rows:
            data[medium][label] = count
        return calculate_entropy(data)

    def quality_scores(self, row):
        """ Counts of source roles per medium, and their entropy. """
        self.scores_ws.write(row, 0, 'Quality')

        rows = []
        names = []
        indicators = [
            'quality_self_help',
            'quality_consequences',
            'quality_solutions',
            'quality_policies',
            'quality_causes',
            'quality_basic_context',
        ]

        for attr in indicators:
            # count documents with this quality
            name = attr.replace('quality_', '').replace('_', ' ').title()
            names.append(name)
            for medium, count in self.filter(
                db.session.query(
                    Medium.name,
                    func.count(1).label('freq'))
                .join(Document)
                .filter(getattr(Document, attr) == True)
                .group_by(Medium.name)
                .order_by(Medium.name)
                ).all():  # noqa

                rows.append([medium, name, count])

        starting_row = row
        row = self.write_score_table(names, rows, row) + 1
        row = self.write_percent_table(names, self.score_row['Total articles'], starting_row, row)

        return row

    def write_percent_row(self, name, denom_row, num_row, row):
        """ Write a row of percentage calculations, using num_row/denom_row. """
        self.write_percent_table([name], denom_row, num_row, row)

    def write_percent_table(self, names, denom_row, starting_row, row):
        """ Write a table of percentages. +denom_row+ is the row of
        the denominator, +starting_row+ is the first row of numerators. """
        formula = lambda r, c: '=IF({{col}}{{denom}}>0,{{col}}{{row}}/{{col}}{{denom}},0)'.format(denom=denom_row + 1, row=r - row + starting_row, col=c)
        names = ['Percent ' + n for n in names]
        return self.write_formula_table(names, formula, row)

    def victim_scores(self, row):
        """ Counts of secondary victimisation per medium """
        self.scores_ws.write(row, 0, 'Secondary Victimisation')

        # number of documents with both a child source, and an
        # abuse victim (secondary victimisation)
        rows = self.filter(
            db.session.query(
                Medium.name,
                func.count(1).label('freq'))
            .join(Document)
            .filter(Document.abuse_victim == True)
            .filter(Document.abuse_source == True)
            .group_by(Medium.name)
            .order_by(Medium.name)
        ).all()  # noqa

        self.write_simple_score_row('Abused sources', rows, row)
        row += 1

        total_row = self.score_row['Total child sources']
        formula = '=IF({{col}}{}>0,{{col}}{}/{{col}}{},0)'.format(total_row + 1, row, total_row + 1)
        self.write_formula_score_row('Percent Abused sources', formula, row)
        row += 1

        formula = '=1-{{col}}{}'.format(row)
        self.write_formula_score_row('Percent Non-abused sources', formula, row)

        return row

    def principle_scores(self, row):
        """ Counts of documents by principle supported, violated """
        principles = Principle.query.all()

        self.scores_ws.write(row, 0, 'Principles supported')
        rows = self.filter(
            db.session.query(
                Medium.name,
                Principle.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(Principle, Document.principle_supported_id == Principle.id)
            .group_by(Medium.name, Principle.name)
        ).all()
        rows = [[r[0], 'S. ' + r[1], r[2]] for r in rows]
        names = ['S. ' + p.name for p in principles]
        row = self.write_score_table(names, rows, row) + 1

        # count of docs with any supported principle
        formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(principles), row - 1)
        self.write_formula_score_row('Rights respected', formula, row)
        row += 1

        # rights respected is the percent of stories that have a supported principle
        total_row = self.score_row['Total articles']
        self.write_percent_row('Rights respected', total_row, row - 1, row)
        row = row + 2

        # percent of documents with each right violated
        formula = lambda r, c: '=IF({{col}}{{tot}}>0,{{col}}{{row}}/{{col}}{{tot}},0)'.format(tot=total_row + 1, row=r - len(names) - 4, col=c)
        names = ['Percent ' + n for n in names]
        row = self.write_formula_table(names, formula, row) + 1

        self.scores_ws.write(row, 0, 'Principles violated')
        rows = self.filter(
            db.session.query(
                Medium.name,
                Principle.name,
                func.count(1).label('freq'))
            .join(Document)
            .join(Principle, Document.principle_violated_id == Principle.id)
            .group_by(Medium.name, Principle.name)
        ).all()
        rows = [[r[0], 'V. ' + r[1], r[2]] for r in rows]
        names = ['V. ' + p.name for p in principles]
        row = self.write_score_table(names, rows, row)

        # count of docs with any violated principle
        formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(principles) + 1, row)
        self.write_formula_score_row('Principles violated', formula, row)
        row += 1
        self.write_percent_row('Principles violated', total_row, row - 1, row)
        row += 1
        self.write_formula_score_row('Inv. Percent Principles violated', '=1-{{col}}{}'.formatrow, row)

        return row

    def write_simple_score_row(self, name, data, row):
        """ Write a single value as a score row, where +data+ is a map from medium name to that value. """
        self.set_score_row(name, row)

        if isinstance(data, list):
            data = {k: v for k, v in data}

        for i, medium in enumerate(self.media):
            medium_col = self.score_col(i)
            self.scores_ws.write(row, medium_col, data.get(medium.name, 0))

    def write_formula_score_row(self, name, formula, row):
        """ Write a single formula as a score row, where +formula+ is a string
        or a lambda. If it's a tsring, it can contain {row} and {col} format strings.
        If a lambda, it will be given row and column as arguments and must
        return the formula string.
        """
        self.set_score_row(name, row)

        if isinstance(formula, str):
            f = formula
            formula = lambda r, c: f.format(row=r, col=c)

        for i, medium in enumerate(self.media):
            medium_col = self.score_col(i)
            col_name = xl_col_to_name(medium_col)
            self.scores_ws.write_formula(row, medium_col, formula(row + 1, col_name))

    def write_score_table(self, row_names, rows, row):
        """ Convert all the rows in +rows+ into a table and write it as scores,
        starting on row number +row+ in the db. +row_names+ is the full set
        of expected row names.

        The table is created by using the first column in +rows+ as the column
        name, and the second as the row name.

        Returns the number of the last row written.
        """
        data = defaultdict(dict)
        for col_name, row_name, val in rows:
            data[row_name][col_name] = val

        for name in row_names:
            self.write_simple_score_row(name, data.get(name, {}), row)
            row = row + 1

        return row

    def write_formula_table(self, row_names, formula, row):
        """ Write a table of formulas, where the row names are in +row_names+
        and the columns are each medium. The +formula+ will have
        {col} and {row} formatted as appropriate.

        Returns the number of the last row written.
        """
        for name in row_names:
            self.write_formula_score_row(name, formula, row)
            row = row + 1

        return row

    def set_score_row(self, name, row):
        """ The row containing the score named +name+ is in +row+. """
        self.score_row[name] = row
        self.scores_ws.write(row, 1, name)

    def build_rating_worksheet(self):
        """ Build up the rating worksheet. """
        # write medium headings
        for i, medium in enumerate(self.media):
            self.rating_ws.write(1, self.rating_col(i), medium.name)

        self.add_nested_ratings(self.ratings, row=3, col=0)

    def add_nested_ratings(self, ratings, row, col):
        rating_rows = []

        for info in ratings:
            weight, rating = info[0:2]

            rating_rows.append(row)
            self.rating_ws.write(row, col, weight)
            self.rating_ws.write(row, col + 1, rating)

            if len(info) > 2:
                # add sub-ratings
                rows, last_row = self.add_nested_ratings(info[2], row + 1, col + 1)

                # now set this rating's score to the product of the children
                col_name = xl_col_to_name(col + 1)
                for i in range(self.n_columns):
                    rating_col_name = xl_col_to_name(self.rating_col(i))
                    # weight * score
                    formula = '+'.join('{}{}*{}{}'.format(col_name, r + 1, rating_col_name, r + 1) for r in rows)
                    self.rating_ws.write_formula(row, self.rating_col(i), formula)

                row = last_row
            else:
                # actual rating
                score_row = self.score_row[rating]

                for i in range(self.n_columns):
                    cell = xl_rowcol_to_cell(score_row, self.score_col(i), row_abs=True, col_abs=True)
                    self.rating_ws.write(row, self.rating_col(i), '=Raw!{}'.format(cell))
            row += 1

        return rating_rows, row

    def source_counts(self, children=False, limit=4):
        # source counts per document
        subq = db.session\
            .query(
                Medium.name.label('medium'),
                func.count(1).label('n_sources'))\
            .join(Document)\
            .join(DocumentSource)\
            .group_by(Medium.name, DocumentSource.doc_id)

        if children:
            subq = subq.filter(DocumentSource.source_type == 'child')

        subq = self.filter(subq).subquery()

        return db.session\
            .query(
                subq.c.medium,
                func.if_(subq.c.n_sources > limit, ">{}".format(limit), subq.c.n_sources).label('bucket'),
                func.count(1))\
            .select_from(subq)\
            .group_by(subq.c.medium, 'bucket')\
            .all()

    def score_col(self, i):
        """ The index of the score for the i-th medium """
        return self.score_col_start + i

    def rating_col(self, i):
        """ The index of the rating for the i-th medium """
        return self.rating_col_start + i

    def filter(self, query):
        return query.filter(Document.id.in_(self.doc_ids))


class MediaDiversityRatingExport(ChildrenRatingExport):
    """ This class generates an XLSX export of per-media ratings.
    """

    ratings = [[1.0, 'Final rating', [
        [0.333, 'Topic', [
            [0.500, 'Diversity of Topics'],
            [0.500, 'Percent Social Justice Focus']]],
        [0.333, 'Region', [
            [1.000, 'Diversity of Regions']]],
        [0.333, 'Sources', [
            [0.250, 'Diversity of Affiliations'],
            [0.250, 'Percent Marginalised Voices'],
            [0.250, 'Gender Ratio'],
            [0.250, 'Avg sources']]],
    ]]]

    def build_scores_worksheet(self):
        """ Build up the scores worksheet. """
        for i, medium in enumerate(self.media):
            self.scores_ws.write(1, self.score_col(i), medium.name)

        row = 4
        row = self.totals(row) + 2
        row = self.taxonomy_scores(row) + 2
        row = self.region_scores(row) + 2
        row = self.sources_scores(row) + 2

        return row

    def taxonomy_scores(self, row):
        """ Counts of document taxonomies per medium, and their entropy. """
        from dexter.models.views import DocumentTaxonomiesView

        self.scores_ws.write(row, 0, 'Topic')

        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentTaxonomiesView.c.label,
                func.count(DocumentTaxonomiesView.c.document_id).label('freq')
            )
            .select_from(DocumentTaxonomiesView)
            .join(Document)
            .join(Medium)
            .group_by(Medium.name, 'label')
        ).all()
        taxonomies = list(set(r[1] for r in rows))
        taxonomies.sort()

        row = self.write_score_table(taxonomies, rows, row) + 1
        self.write_simple_score_row('Diversity of Topics', self.entropy(rows), row)
        row += 2

        # social justice focus bonus
        focus = ['Education', 'Environment', 'Health', 'Labour', 'Social Issues']
        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentTaxonomiesView.c.label,
                func.count(DocumentTaxonomiesView.c.document_id).label('freq')
            )
            .select_from(DocumentTaxonomiesView)
            .join(Document)
            .join(Medium)
            .filter(DocumentTaxonomiesView.c.label.in_(focus))
            .group_by(Medium.name, 'label')
        ).all()

        taxonomies = list(set(r[1] for r in rows))
        taxonomies.sort()

        row = self.write_score_table(taxonomies, rows, row) + 1
        formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(taxonomies), row - 1)
        self.write_formula_score_row('Social Justice Focus', formula, row)
        row += 1
        self.write_percent_row('Social Justice Focus', self.score_row['Total articles'], row - 1, row)

        row += 1

        return row

    def region_scores(self, row):
        """ Counts of document regions per medium, and their entropy. """
        from dexter.models.views import DocumentPlacesView

        self.scores_ws.write(row, 0, 'Region')

        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentPlacesView.c.province_name,
                func.count(1).label('freq')
            )
            .select_from(DocumentPlacesView)
            .join(Document)
            .join(Medium)
            .group_by(Medium.name, DocumentPlacesView.c.province_name)
        ).all()
        regions = list(set(r[1] for r in rows))
        regions.sort()

        row = self.write_score_table(regions, rows, row) + 1
        self.write_simple_score_row('Diversity of Regions', self.entropy(rows), row)
        row += 1

        return row

    def sources_scores(self, row):
        """ Counts of genders of sources """
        from dexter.models.views import DocumentSourcesView
        self.scores_ws.write(row, 0, 'Sources')

        # source affiliations
        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentSourcesView.c.affiliation_group.label('affiliation'),
                func.count(1).label('freq'))
            .select_from(DocumentSourcesView)
            .join(Document)
            .join(Medium)
            .group_by(Medium.name, DocumentSourcesView.c.affiliation_group)
            .order_by(Medium.name)
        ).all()

        affiliations = list(set(r[1] for r in rows))
        affiliations.sort()

        row = self.write_score_table(affiliations, rows, row) + 1
        self.write_simple_score_row('Diversity of Affiliations', self.entropy(rows), row)

        row += 2

        # marginalised voices
        focus_groups = ['Citizens', 'Academics / Experts / Researchers', 'NGOs / CBOs / FBOs', 'Unions']
        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentSourcesView.c.affiliation_group.label('affiliation'),
                func.count(1).label('freq'))
            .select_from(DocumentSourcesView)
            .join(Document)
            .join(Medium)
            .filter(DocumentSourcesView.c.affiliation_group.in_(focus_groups))
            .group_by(Medium.name, DocumentSourcesView.c.affiliation_group)
            .order_by(Medium.name)
        ).all()

        affiliations = list(set(r[1] for r in rows))
        affiliations.sort()

        row = self.write_score_table(affiliations, rows, row) + 1
        formula = '=SUM({{col}}{}:{{col}}{})'.format(row - len(affiliations), row - 1)
        self.write_formula_score_row('Marginalised Voices', formula, row)
        row += 1
        self.write_percent_row('Marginalised Voices', self.score_row['Total sources'], row - 1, row)

        row += 2

        # gender diversity
        rows = self.filter(
            db.session.query(
                Medium.name,
                DocumentSourcesView.c.gender,
                func.count(1).label('freq'))
            .select_from(DocumentSourcesView)
            .join(Document, DocumentSourcesView.c.document_id == Document.id)
            .join(Medium)
            .group_by(Medium.name, DocumentSourcesView.c.gender)
            .order_by(Medium.name)
        ).all()

        rows = [[m, g or 'Unknown', c] for m, g, c in rows]
        genders = set(r[1] for r in rows)
        genders.update(['Male', 'Female'])
        genders = list(genders)
        genders.sort()

        row = self.write_score_table(genders, rows, row) + 1

        # male / female ratio
        male, female = self.score_row['Male'], self.score_row['Female']
        formula = '=IF({{col}}{}>0,{{col}}{}/{{col}}{},0)'.format(male + 1, female + 1, male + 1)
        self.write_formula_score_row('Male to female', formula, row)
        row += 1
        formula = '=IF({{col}}{}>1,1/{{col}}{},{{col}}{})'.format(row, row, row)
        self.write_formula_score_row('Gender Ratio', formula, row)
        row += 2

        # avg sources per medium
        doc_counts = self.filter(
            db.session.query(
                Document.medium_id,
                func.count(1).label('doc_count'))
            .group_by(Document.medium_id)).subquery()

        source_counts = self.filter(
            db.session.query(
                Document.medium_id,
                func.count(1).label('source_count'))
            .select_from(DocumentSource)
            .join(Document)
            .group_by(Document.medium_id)).subquery()

        rows = db.session.query(
            Medium.name,
            source_counts.c.source_count / doc_counts.c.doc_count)\
            .join(source_counts, Medium.id == source_counts.c.medium_id)\
            .join(doc_counts, Medium.id == doc_counts.c.medium_id)\
            .all()

        self.write_simple_score_row('Avg sources', rows, row)
        row += 2

        return row
