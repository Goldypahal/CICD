from click.testing import CliRunner
from gitfix.cli import cli

def test_cli_init_and_analyze():
    runner = CliRunner()
    with runner.isolated_filesystem():
        res_init = runner.invoke(cli, ["init"])
        assert res_init.exit_code == 0
        assert "GitFix-Agent Initialized" in res_init.output

        res_analyze = runner.invoke(cli, ["analyze"])
        assert res_analyze.exit_code == 0
        assert "GitFix Project Inspection" in res_analyze.output
