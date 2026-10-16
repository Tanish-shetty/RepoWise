"""Initial RepoWise schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None


def upgrade():
    op.create_table("repositories", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(200)),
        sa.Column("source", sa.Text()), sa.Column("local_path", sa.Text()), sa.Column("status", sa.String(40)),
        sa.Column("profile", sa.JSON()), sa.Column("created_at", sa.DateTime()))
    op.create_table("analysis_runs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id")), sa.Column("kind", sa.String(30)),
        sa.Column("status", sa.String(30)), sa.Column("request", sa.Text()), sa.Column("result", sa.JSON()),
        sa.Column("created_at", sa.DateTime()))
    op.create_table("generated_tests", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("analysis_runs.id")), sa.Column("file_path", sa.Text()), sa.Column("content", sa.Text()))
    op.create_table("test_runs", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), sa.ForeignKey("repositories.id")), sa.Column("status", sa.String(30)),
        sa.Column("exit_code", sa.Integer()), sa.Column("duration_ms", sa.Integer()), sa.Column("output", sa.Text()))


def downgrade():
    for table in ("test_runs", "generated_tests", "analysis_runs", "repositories"):
        op.drop_table(table)

