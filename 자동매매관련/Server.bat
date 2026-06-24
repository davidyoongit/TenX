@echo off
@cd C:\Users\dream\PycharmProjects\SystemTrading
call C:\Users\dream\PycharmProjects\SystemTrading\venv\Scripts\activate
@python .\Investar\manage.py runserver --noreload --nothreading 192.168.1.113:8000