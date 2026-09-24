"""floodflow.wbt: exit codes are checked and panics retried (fake WBT binary)."""

import stat

import pytest

from floodflow import wbt


@pytest.fixture
def fake_wbt(tmp_path, monkeypatch):
    """A stand-in `whitebox_tools` whose behaviour is scripted per call."""
    def install(script_body: str):
        exe = tmp_path / "whitebox_tools"
        exe.write_text("#!/bin/sh\n" + script_body)
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        monkeypatch.setattr(wbt, "_exe", lambda: exe)
        return exe
    return install


def _output_arg():
    # The fake finds --output=... among its args and writes it.
    return 'for a in "$@"; do case $a in --output=*) out=${a#--output=};; esac; done\n'


def test_success_requires_exit_zero_and_output(tmp_path, fake_wbt):
    fake_wbt(_output_arg() + 'echo ok > "$out"\n')
    out = wbt.run("FillDepressions", tmp_path / "f.tif", dem=tmp_path / "d.tif", fix_flats=True)
    assert out.exists()


def test_panic_is_retried(tmp_path, fake_wbt):
    counter = tmp_path / "calls"
    fake_wbt(_output_arg() + f'''
n=$(cat {counter} 2>/dev/null || echo 0); n=$((n+1)); echo $n > {counter}
if [ $n -lt 3 ]; then echo "thread 'main' panicked" >&2; exit 101; fi
echo ok > "$out"
''')
    out = wbt.run("FillDepressions", tmp_path / "f.tif", dem=tmp_path / "d.tif")
    assert out.exists() and counter.read_text().strip() == "3"


def test_persistent_panic_raises(tmp_path, fake_wbt):
    fake_wbt('echo "thread main panicked at fill_depressions.rs" >&2; exit 101\n')
    with pytest.raises(RuntimeError, match="exit 101.*\n.*panicked"):
        wbt.run("FillDepressions", tmp_path / "f.tif", dem=tmp_path / "d.tif")


def test_exit_zero_without_output_raises(tmp_path, fake_wbt):
    # the wrapper's old failure mode: "success" with nothing written
    fake_wbt("exit 0\n")
    with pytest.raises(RuntimeError, match="output missing"):
        wbt.run("ExtractStreams", tmp_path / "s.tif", flow_accum=tmp_path / "a.tif")


def test_other_errors_are_not_retried(tmp_path, fake_wbt):
    counter = tmp_path / "calls"
    fake_wbt(f'echo x >> {counter}; echo "Error: bad input" >&2; exit 1\n')
    with pytest.raises(RuntimeError, match="bad input"):
        wbt.run("D8Pointer", tmp_path / "p.tif", dem=tmp_path / "d.tif")
    assert len(counter.read_text().splitlines()) == 1


def test_flags(tmp_path):
    assert wbt._flag("fix_flats", True) == "--fix_flats"
    assert wbt._flag("fix_flats", False) is None
    assert wbt._flag("threshold", 250) == "--threshold=250"
    assert wbt._flag("dem", tmp_path / "x.tif") == f"--dem={(tmp_path / 'x.tif').resolve()}"
