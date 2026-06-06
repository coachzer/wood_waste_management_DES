"""Persistence space: the one serializer + jsonify encoder.

Reads instrumentation state and writes the raw sidecars analysis consumes.
Holds ``serialization`` (the jsonify encoder + raw-payload builder); import the
concrete submodule (``from persistence.serialization import jsonify``) rather
than the package root.
"""
