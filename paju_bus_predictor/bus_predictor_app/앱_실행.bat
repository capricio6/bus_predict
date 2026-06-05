@echo off
cd /d "%~dp0"
echo 파주 버스 관측 예측 앱을 시작합니다.
echo.
echo PC에서는 http://127.0.0.1:8765 를 열어 주세요.
echo 휴대폰에서는 아래 IPv4 주소 중 Wi-Fi 주소로 접속하세요.
echo 예: http://192.168.0.12:8765
echo.
ipconfig | findstr /i "IPv4"
echo.
start "" "http://127.0.0.1:8765"
python server.py
