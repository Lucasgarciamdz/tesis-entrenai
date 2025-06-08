iniciar:
	uvicorn entrenai_refactor.api.principal:app --reload

iniciar-celery:
	celery -A entrenai_refactor.celery.aplicacion_celery.app worker --loglevel=info

prueba:
	echo "Prueba de Makefile: todo funcionando en español" 