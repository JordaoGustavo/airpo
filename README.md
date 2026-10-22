# airpo — AirPods no Linux, no estilo do macOS

- Bateria do fone esquerdo, do direito e da caixinha (na bandeja e via `airpo status`)
- Modos de ruído: Cancelamento de ruído, Transparência, Adaptativo (só no Pro 2) e Desligado
- Conexão automática ao abrir a caixinha perto do Linux, e "Conectar a este computador" com um clique
- O áudio vai sozinho para os AirPods (perfil A2DP e saída padrão)

## Como funciona

| Recurso | Como |
|---|---|
| Bateria/ruído quando conectado | Protocolo AAP da Apple (L2CAP PSM 0x1001), o mesmo do [LibrePods](https://github.com/kavishdevar/librepods) |
| Bateria quando conectado ao Mac | Anúncios BLE "proximity pairing" (tipo 0x07, Apple 0x004C) |
| Troca automática | Ao ver os AirPods reaparecerem por perto (caixinha aberta) e com você usando o Linux, ele conecta e "toma" os fones do Mac |

A troca da Apple usa iCloud entre os aparelhos, e o Linux não participa disso. Por isso:
- **Mac → Linux**: automático (abriu a caixinha perto do Linux), ou pelo menu da bandeja, ou com `airpo connect`. Dá pra pôr esse comando num atalho de teclado.
- **Linux → Mac**: escolha os AirPods no menu de Bluetooth/Som do Mac, como você já faz.

## Instalação (no Linux)

1. Dependências (Ubuntu):
   ```
   sudo apt install bluez pipewire-pulse python3-pip python3-gi gir1.2-ayatanaappindicator3-0.1 gnome-shell-extension-appindicator
   ```
   O ícone fica na barra de cima, ao lado do relógio, com a bateria do lado (🎧 80%), como no Mac. No Ubuntu a extensão AppIndicator já vem ligada. Em GNOME puro, ative "AppIndicator" no app Extensões.
2. Pareie uma vez: com os fones na caixinha aberta, segure o botão de trás até a luz piscar em branco. Depois rode `bluetoothctl` → `scan on` → `pair <MAC>` → `trust <MAC>`.
   Os AirPods guardam vários pareamentos, então o do Mac continua valendo.
3. Opcional, mas recomendado: em `/etc/bluetooth/main.conf`, na seção `[General]`:
   ```
   DeviceID = bluetooth:004C:0000:0000
   ```
   Isso faz o Linux se apresentar como um aparelho Apple, e alguns recursos do AAP só respondem assim. Depois rode `sudo systemctl restart bluetooth`.
4. `./install.sh`

## No Mac

Ajustes do Sistema → Bluetooth → (i) dos AirPods → **Conectar a este Mac: "Quando conectado pela última vez a este Mac"**.
Sem isso, o Mac pode tomar os fones de volta logo depois que o Linux conectar.

## Uso

```
airpo status            # Left: 80%  Right: 90%  Case: 40% ⚡
airpo connect           # trazer os fones para o Linux
airpo disconnect
airpo anc | transparency | off
```

Configuração em `~/.config/airpo/config.toml`: MAC, auto_connect, sensibilidade de sinal, tempo ocioso e modo de ruído padrão.
Logs: `journalctl --user -u airpo -f`
