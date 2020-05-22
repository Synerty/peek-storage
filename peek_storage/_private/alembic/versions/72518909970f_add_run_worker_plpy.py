"""add run worker plpy

Revision ID: 72518909970f
Revises: bab14faf0cd7
Create Date: 2020-05-20 20:13:19.092876

"""

# revision identifiers, used by Alembic.

revision = '72518909970f'
down_revision = '12a0ab3826f3'
branch_labels = None
depends_on = None

from alembic import op

def upgrade():
    sql = '''
CREATE OR REPLACE FUNCTION peek_storage.run_worker_task_python(
    sqla_url character varying,
    args_json character varying,
    class_method_to_run_str_ character varying,
    python_path character varying)
    RETURNS character varying
    LANGUAGE 'plpython3u'

    COST 100
    VOLATILE

AS $BODY$

import json
from base64 import b64decode
sqlaUrl = sqla_url
argsJson = args_json
classMethodToRunStr = class_method_to_run_str_
pythonPath = json.loads(python_path)

# ---------------
# Setup Config

import sys

if not GD.get('peek_sys_path_set'):
    sys.path.extend(pythonPath)
    GD['peek_sys_path_set'] = True

# ---------------
# Setup to use the virtual environment

if GD.get('peek_config'):
    config = GD['peek_config']

else:
    from peek_plugin_base.PeekVortexUtil import peekWorkerName
    from peek_worker.PeekWorkerConfig import PeekWorkerConfig

    from peek_platform import PeekPlatformConfig
    PeekPlatformConfig.componentName = peekWorkerName

    config = PeekWorkerConfig()
    GD['peek_config'] = config

# ---------------
# Setup the workers logger

if not GD.get('peek_logger_setup'):
    import logging
    import os
    from peek_plugin_base.PeekVortexUtil import peekWorkerName
    from peek_platform.util.LogUtil import setupPeekLogger

    logging.root.setLevel(config.loggingLevel)

    setupPeekLogger("%s-%s" % (peekWorkerName, os.getpid()))
    GD['peek_logger_setup'] = True

# ---------------
# Initialise the DB Connections

if GD.get('CeleryDbConn'):
    CeleryDbConn = GD['CeleryDbConn']

else:
    from peek_plugin_base.worker import CeleryDbConn
    CeleryDbConn._dbConnectString = sqlaUrl
    CeleryDbConn._dbEngineArgs = {
        "max_overflow": 1,
        "pool_recycle": 600,
        "pool_size": 1,
        "pool_timeout": 0
    }

# ---------------
# Dynamically load the tuple create method

if GD.get(classMethodToRunStr):
    moduleMethodToRun = GD[classMethodToRunStr]

else:
    from importlib.util import find_spec, module_from_spec

    modName, methodName = classMethodToRunStr.rsplit('.',1)

    if modName in sys.modules:
        package_ = sys.modules[modName]

    else:
        modSpec = find_spec(modName)
        if not modSpec:
             raise Exception("Failed to find package %s,"
                               " is the python package installed?" % modName)
        package_ = modSpec.loader.load_module()

    moduleMethodToRun = getattr(package_, methodName)

# ---------------
# Load the arguments


if GD.get('peek_ArgTuple'):
    _RunPyInWorkerArgsTuple = GD['peek_ArgTuple']
    _RunPyInWorkerResultTuple = GD['peek_ResultTuple']
    json = GD['peek_json']

else:
    from peek_storage.plpython.RunWorkerTaskPyInPg \
        import _RunPyInWorkerArgsTuple, _RunPyInWorkerResultTuple

    GD['peek_ArgTuple'] = _RunPyInWorkerArgsTuple
    GD['peek_ResultTuple'] = _RunPyInWorkerResultTuple

    import json
    GD['peek_json'] = json

argsTuple = _RunPyInWorkerArgsTuple().fromJsonDict(json.loads(argsJson))

# ---------------
# Run the worker task

result = moduleMethodToRun(*argsTuple.args, **argsTuple.kwargs)

return json.dumps(_RunPyInWorkerResultTuple(result=result).toJsonDict())

$BODY$;

ALTER FUNCTION peek_storage.run_worker_task_python(character varying, character varying,
                                                   character varying, character varying)
    OWNER TO peek;


          '''
    op.execute(sql)


def downgrade():
    sql = '''DROP FUNCTION peek_storage.run_worker_task_python(character varying,
                                                               character varying,
                                                               character varying,
                                                               character varying);'''
    op.execute(sql)
