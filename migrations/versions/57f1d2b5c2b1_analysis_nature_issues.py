"""analysis nature issues

Revision ID: 57f1d2b5c2b1
Revises: 3421025b5e5e
Create Date: 2015-08-12 18:02:34.537329

"""

# revision identifiers, used by Alembic.
revision = '57f1d2b5c2b1'
down_revision = '3421025b5e5e'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.create_table('analysis_nature_issues',
    sa.Column('analysis_nature_id', sa.Integer(), nullable=True),
    sa.Column('issue_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['analysis_nature_id'], ['analysis_natures.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['issue_id'], ['issues.id'], ondelete='CASCADE')
    )
    ### end Alembic commands ###

    # issues with an analysis nature
    op.execute("INSERT INTO analysis_nature_issues (analysis_nature_id, issue_id)" +
               " SELECT analysis_nature_id, id from issues where analysis_nature_id is not null")

    # issues for all analysis natures
    from dexter.models import AnalysisNature
    for nature in AnalysisNature.all():
        op.execute("INSERT INTO analysis_nature_issues (analysis_nature_id, issue_id)" +
                   " SELECT %d, id from issues where analysis_nature_id is null" % nature.id)


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('analysis_nature_issues')
    ### end Alembic commands ###
