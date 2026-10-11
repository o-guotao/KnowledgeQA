"""merge 0015_model_config_protocol and 0016_rbac_acl

Revision ID: 874ca5407d66
Revises: 0015_model_config_protocol, 0016_rbac_acl
Create Date: 2026-10-11 07:10:06.724263

"""
from alembic import op
import sqlalchemy as sa


revision = '874ca5407d66'
down_revision = ('0015_model_config_protocol', '0016_rbac_acl')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
