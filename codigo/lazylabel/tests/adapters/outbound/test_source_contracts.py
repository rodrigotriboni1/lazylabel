"""Real adapter contracts: projection, immutable sources, and configured types."""
import sqlite3

import pytest


def adapters():
    from lazylabel.adapters.outbound.persistence.projects import FileProjectLookup
    from lazylabel.adapters.outbound.sources.reader import LocalSourceReader
    return FileProjectLookup(), LocalSourceReader()


@pytest.mark.parametrize('kind', ['csv', 'sqlite'])
def test_project_source_adapters_project_selected_values_without_mutating_source(tmp_path, kind):
    from lazylabel.project import init_project, save_project
    from lazylabel.sources.base import ProjectConfig, SourceSpec
    config_path = init_project(tmp_path)
    if kind == 'csv':
        path = tmp_path / 'ledger.csv'
        path.write_bytes(b'id,amount,secret\na,10,private\nb,20,hidden\n')
        spec = SourceSpec('ledger', kind, path, schema={'amount': 'decimal'})
    else:
        path = tmp_path / 'ledger.db'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE ledger(id TEXT PRIMARY KEY, amount INTEGER, secret TEXT)')
            db.executemany('INSERT INTO ledger VALUES (?, ?, ?)', [('a', 10, 'private'), ('b', 20, 'hidden')])
        spec = SourceSpec('ledger', kind, path, table='ledger', id_column='id', schema={'amount': 'decimal'})
    save_project(ProjectConfig(config_path, {'ledger': spec}, {}, config_path.parent), config_path)
    original = path.read_bytes()
    projects, sources = adapters()
    from lazylabel.application.use_cases.projects import get_project, iter_project_records
    descriptor = get_project(projects, str(tmp_path))
    assert tuple(descriptor.source_names) == ('ledger',)
    source = sources.open_source(str(tmp_path), 'ledger')
    assert source.explicit_types == {'amount': 'decimal'}
    assert source.capabilities().read_only
    records = list(iter_project_records(projects, sources, str(tmp_path), 'ledger', ['amount'], batch_size=1))
    assert [str(row.values['amount']) for row in records] == ['10', '20']
    assert all(set(row.values) == {'amount'} for row in records)
    assert all(len(row.input_digest) == 64 for row in records)
    assert len(source.columns()) == 3
    assert path.read_bytes() == original
    if kind == 'sqlite':
        with pytest.raises(sqlite3.OperationalError):
            with source._connect() as db:
                db.execute('DELETE FROM ledger')
        assert path.read_bytes() == original


def test_unknown_source_preserves_lookup_exception(tmp_path):
    from lazylabel.project import init_project
    init_project(tmp_path)
    _, sources = adapters()
    with pytest.raises(KeyError, match='Unknown source'):
        sources.open_source(str(tmp_path), 'absent')


def test_legacy_capabilities_require_all_flags_and_records_cross_application_boundary():
    from lazylabel.sources.base import SourceCapabilities, SourceRecord
    from lazylabel.application.ports.sources import SourceRecord as ApplicationRecord
    with pytest.raises(TypeError):
        SourceCapabilities()
    assert isinstance(SourceRecord('id', {}, 'digest'), ApplicationRecord)
