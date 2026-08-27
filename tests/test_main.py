from rap_senfab.main import main


def test_main_runs(capsys):
    main()
    captured = capsys.readouterr()
    assert "Hello from rap-senfab!" in captured.out
