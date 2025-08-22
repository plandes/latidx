#@meta {desc: 'build and deployment for python projects', date: '2024-03-25'}


## Build system
#
#
# type of project
PROJ_TYPE =		python
PROJ_MODULES =		python/doc python/package python/deploy


## Includes
#
include ./zenbuild/main.mk


## Targets
#
.PHONY:			listdeps
listdeps:
			$(eval PY_CLI_ARGS=deps $(PY_CLI_ARGS))
			@make PY_CLI_DEBUG=1 PY_CLI_ARGS="$(PY_CLI_ARGS)" pycli
