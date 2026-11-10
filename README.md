[![Otwórz repozytorium w HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=LukaszP2&repository=ha-gen-gaz&category=integration)
[![Dodaj integrację do Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=gen_gaz)

G.EN. Gaz Energia 0.7.0

Historia odczytów oraz usługa update_advance_plan z polami formularza HA.

## Instalacja

### 🚀 Szybka instalacja (1 kliknięcie przez My Home Assistant)

[![Otwórz repozytorium w HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=LukaszP2&repository=ha-gen-gaz&category=integration)

Po zainstalowaniu i ponownym uruchomieniu Home Assistant, kliknij poniższy przycisk, aby skonfigurować integrację:

[![Dodaj integrację do Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=gen_gaz)

---

## Gotowe szablony automatyzacji (Blueprints)

W katalogu `blueprints/automation/gen_gaz/` dostępne są gotowe szablony automatyzacji:

1. **Przypomnienie o terminie płatności faktury / zaliczki** (`payment_due_reminder.yaml`):
   Codziennie sprawdza termin płatności najnowszego rachunku i wysyła alert na telefon z wyprzedzeniem (np. 3 dni i/lub 1 dzień przed terminem).
2. **Alert o wystawieniu nowej faktury** (`new_invoice_alert.yaml`):
   Natychmiastowe powiadomienie z kwotą, numerem dokumentu i terminem płatności po pojawieniu się nowej faktury w eBOK.
3. **Ostrzeżenie o niedopłacie w planie zaliczkowym** (`advance_plan_deviation.yaml`):
   Ostrzega, gdy rzeczywisty koszt zużytego gazu przewyższa sumę zaliczek o ustalony próg (np. > 150 PLN), sugerując korektę planu zaliczek.
4. **Przypomnienie o podaniu odczytu licznika** (`meter_reading_reminder.yaml`):
   Cykliczne przypomnienie o spisaniu i wprowadzeniu stanu gazomierza pod koniec okresu rozliczeniowego lub po upływie określonej liczby dni bez odczytu.
5. **Alert o nietypowo wysokim zużyciu gazu** (`high_gas_consumption_alert.yaml`):
   Alarm krytyczny wysyłany w przypadku przekroczenia bezpiecznego progu zużycia gazu w m³ (pomaga wykryć awarie kotła lub nieszczelności).
6. **Powiadomienie o nowej wiadomości w eBOK** (`unread_messages_alert.yaml`):
   Powiadomienie o nowej korespondencji od operatora G.EN. Gaz w portalu eBOK.
