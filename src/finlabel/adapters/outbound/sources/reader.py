"""Resolve named project sources using the local read-only implementations."""
from finlabel.adapters.outbound.persistence.projects import load_project, open_source


class LocalSourceReader:
    def open_source(self, project_reference, source_name):
        return open_source(load_project(project_reference), source_name)
