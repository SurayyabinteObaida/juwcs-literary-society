"""remap users.theme onto the five-theme system

Revision ID: a1c5f0e2b7d4
Revises: 0e3ae1f2ea66
Create Date: 2026-08-16 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c5f0e2b7d4'
down_revision = '0e3ae1f2ea66'
branch_labels = None
depends_on = None


# Old theme slug -> one of the five current theme slugs.
LEGACY_TO_NEW = {
    'classic-light': 'classic-literary',
    'paper-ink': 'classic-literary',
    'classic-sepia': 'classic-literary',
    'literary-teal': 'literary-green',
    'editorial-ivory': 'literary-green',
    'royal': 'royal-blue',
    'midnight-dark': 'midnight',
}
NEW_THEMES = {'classic-literary', 'literary-green', 'royal-blue', 'rose-poetry', 'midnight'}


def upgrade():
    users = sa.table('users', sa.column('id', sa.Integer), sa.column('theme', sa.String))
    conn = op.get_bind()

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('theme', server_default='classic-literary')

    for old, new in LEGACY_TO_NEW.items():
        conn.execute(users.update().where(users.c.theme == old).values(theme=new))

    # Anything left over that isn't one of the five valid slugs falls back
    # to the new default rather than being silently coerced at read-time only.
    conn.execute(
        sa.text(
            "UPDATE users SET theme = 'classic-literary' "
            "WHERE theme NOT IN ('classic-literary', 'literary-green', 'royal-blue', 'rose-poetry', 'midnight')"
        )
    )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('theme', server_default='classic-light')
