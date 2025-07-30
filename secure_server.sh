#!/bin/bash

echo "[1/7] Обновление пакетов..."
sudo apt update && sudo apt upgrade -y

echo "[2/7] Настройка UFW (firewall)..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22        # SSH
sudo ufw allow 80        # HTTP
sudo ufw allow 443       # HTTPS
sudo ufw --force enable
sudo ufw status verbose

echo "[3/7] Установка Fail2Ban..."
sudo apt install fail2ban -y
sudo systemctl enable fail2ban --now

echo "[3.1] Конфигурация Fail2Ban (jail.local)..."
cat <<EOF | sudo tee /etc/fail2ban/jail.local > /dev/null
[sshd]
enabled = true
port    = ssh
filter  = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
EOF

sudo systemctl restart fail2ban

echo "[4/7] Установка Portsentry..."
sudo apt install portsentry -y
sudo systemctl enable portsentry --now

echo "[4.1] Конфигурация Portsentry..."
sudo sed -i 's/^TCP_MODE="tcp"/TCP_MODE="atcp"/' /etc/default/portsentry
sudo sed -i 's/^UDP_MODE="udp"/UDP_MODE="audp"/' /etc/default/portsentry
sudo systemctl restart portsentry

echo "[5/7] Защита от базовых DoS через iptables..."
sudo iptables -A INPUT -p tcp --syn --dport 80 -m connlimit --connlimit-above 30 -j DROP
sudo iptables -A INPUT -p tcp --syn --dport 443 -m connlimit --connlimit-above 30 -j DROP

echo "[5.1] Сохранение iptables..."
sudo apt install iptables-persistent -y
sudo netfilter-persistent save

echo "[6/7] Установка iftop и nethogs (мониторинг)..."
sudo apt install iftop nethogs -y

echo "[7/7] Готово! Сервер защищен базовыми средствами безопасности ✅"
