# Parity with MeshSat Android

MeshSat Android is the reference, pinned at `v2.19.4`. One row per screen, tab, card, dialog, banner and notification of the Android app; a row is done when the Linux app has it, in Android's words, and a test proves it. Kept by `tools/parity-check.py` from `tests/parity/ledger.json`; the words by `tools/android-strings.py`.

**Rows:** 96: 24 missing, 24 partial, 20 built, 18 verified, 8 excluded, 2 blocked.

**Words:** 459 of 1410 readable strings of Android's `ui/` and `sos/` are in the Linux sources, 0 excluded with a reason, 951 still to port.

States: `missing` (not there), `partial` (some of it), `built` (there, untested), `verified` (there, in Android's words, with a test that ran green on the phone), `excluded` (not ported, with the reason), `blocked` (built and tested against the scripted Bridge, waiting for hardware the bench lacks).

| id | kind | Android | Linux | modes | state | test | note |
|---|---|---|---|---|---|---|---|
| shell.strip | banner | `ui/MeshSatUI.kt:330-352` | `widgets.py:StatusStrip` | both | verified | h_home::sentence_and_lanes_follow_the_bridge | the five items with Android's descriptions |
| shell.navbar | banner | `ui/MeshSatUI.kt:Tab` | `widgets.py:NavBar` | both | verified | h_shell::every_route_opens_and_fits_the_screen |  |
| shell.banner.node | banner | `ui/components/NodeLinkBanner.kt` | `__main__.py:on_state` | both | built |  | the 'Bluetooth is off' state waits for Bridge change B13 |
| shell.banner.sos | banner | `ui/screens/SosScreens.kt` | `__main__.py:on_state` | both | verified | h_home::sos_confirmed_activates_and_can_be_cancelled |  |
| shell.night | behaviour | `ui/theme/NightMode.kt` | `widgets.py:Filtered` | both | verified | h_shell::night_mode_toggles_and_is_remembered |  |
| shell.routes | behaviour | `ui/MeshSatUI.kt:tabOf` | `routes.py` | both | verified | RoutesTest.test_android_routes_have_their_tab |  |
| home | screen | `ui/screens/DashboardScreen.kt` | `home.py:HomeScreen` | both | partial |  | the mailbox, position and chart cards and Arrange Home are still to come (0.12.0) |
| home.sentence | card | `ui/screens/HomeLanes.kt:223-240` | `model/home.py:sentence` | both | verified | h_home::sentence_and_lanes_follow_the_bridge |  |
| home.lane.satellite | card | `ui/screens/HomeLanes.kt:150-180` | `model/home.py:satellite_lane` | both | partial | h_home::sentence_and_lanes_follow_the_bridge | the pass line and the node's modem states wait for B9 (0.12.0) |
| home.lane.mesh | card | `ui/screens/HomeLanes.kt:183-198` | `model/home.py:mesh_lane` | both | verified | h_home::sentence_and_lanes_follow_the_bridge |  |
| home.lane.sms | card | `ui/screens/HomeLanes.kt:200-208` | `model/home.py:sms_lane` | both | verified | h_home::sentence_and_lanes_follow_the_bridge |  |
| home.lane.hub | card | `ui/screens/HomeLanes.kt:215-222` | `model/home.py:hub_lane` | both | partial | h_home::sentence_and_lanes_follow_the_bridge | Connected/Error/Disconnected wait for Bridge change B12 |
| home.lane.taps | behaviour | `ui/screens/HomeLanes.kt:261,272` | `__main__.py:open_lane` | both | built |  |  |
| home.checklist | card | `ui/screens/Onboarding.kt:133-195` | `model/home.py:checklist` | both | partial |  | 'Hide' is still to come |
| home.sos-card | card | `ui/screens/SosScreens.kt:SosCard` | `home.py:HomeScreen` | both | partial | h_home::sos_confirmed_activates_and_can_be_cancelled | 'Test the alarm', the progress summary and 'Stop test' come with 0.6.0 |
| home.sos.hold | behaviour | `ui/components/HoldToSend.kt` | `widgets.py:HoldButton` | both | verified | h_home::sos_hold_bar_asks_before_sending_when_activated_by_name | the accessible activation asks first, as Android's |
| home.sos.send-dialog | dialog | `ui/screens/SosScreens.kt:389-399` | `home.py:sos_activate` | both | verified | h_home::sos_hold_bar_asks_before_sending_when_activated_by_name |  |
| home.sos.cancel-dialog | dialog | `ui/screens/SosScreens.kt:403-411` | `home.py:sos_cancel_asked` | both | verified | h_home::sos_confirmed_activates_and_can_be_cancelled |  |
| home.signal-history | card | `ui/screens/DashboardScreen.kt:signal` | `home.py:draw_chart` | both | built |  |  |
| home.recent | card | `ui/screens/DashboardScreen.kt:recent` | `home.py:update` | both | built |  |  |
| home.arrange | dialog | `ui/screens/DashboardScreen.kt:ReorderDialog` | `` | both | missing |  | 0.12.0 |
| home.card.mailbox | card | `ui/screens/DashboardScreen.kt:229-260` | `` | both | missing |  | 0.12.0 |
| home.card.position | card | `ui/screens/DashboardScreen.kt:275-310` | `` | both | missing |  | 0.12.0 |
| home.card.charts | card | `ui/screens/DashboardScreen.kt:311-372` | `` | both | missing |  | 0.12.0 |
| messages | screen | `ui/screens/MessagesScreen.kt` | `messages.py:MessagesScreen` | both | partial | h_messages::counts_have_a_singular | search and delivery ticks come with 0.7.0 |
| messages.new-message | dialog | `ui/screens/MessagesScreen.kt:NewMessageDialog` | `messages.py:new_message` | both | verified | h_messages::new_message_to_a_node_opens_that_node |  |
| messages.search | behaviour | `ui/screens/MessagesScreen.kt:search` | `` | both | missing |  | 0.7.0 |
| chat | screen | `ui/screens/MessagesScreen.kt:ChatScreen` | `messages.py:ChatScreen` | both | partial | h_chat::send_posts_once_and_shows_the_bubble | the composer's placeholders, footer lines and marks come with 0.7.0 |
| chat.send | behaviour | `ui/screens/MessagesScreen.kt:send` | `messages.py:ChatScreen.send` | both | verified | h_chat::send_posts_once_and_shows_the_bubble |  |
| chat.failed-send | behaviour | `ui/screens/MessagesScreen.kt:send` | `messages.py:ChatScreen.send` | both | verified | h_chat::a_failed_send_keeps_the_text_and_says_why |  |
| chat.composer-words | strings | `ui/screens/MessagesScreen.kt:589-719` | `` | both | missing |  | 0.7.0 |
| chat.ticks | behaviour | `ui/components/DeliveryMark` | `` | both | missing |  | 0.7.0 |
| chat.key | sheet | `ui/screens/SettingsScreen.kt:KeyManagementSection` | `` | both | missing |  | 0.12.0 |
| map | screen | `ui/screens/MapScreen.kt` | `mapview.py:MapScreen` | both | partial |  | the phone row, the toasts and Show on map come with 0.10.0 |
| map.chrome | card | `ui/components/MapChrome.kt` | `mapview.py:MapScreen` | both | partial |  | the offline-map notes come with 0.10.0 |
| map.panel | card | `ui/components/MapChrome.kt:layers` | `mapview.py:update` | both | built |  | layers and per-node hide |
| map.tracks | behaviour | `map/MapTracks.kt` | `` | both | missing |  | 0.10.0 |
| people | screen | `ui/screens/PeersScreen.kt` | `people.py:PeopleScreen` | both | partial | h_names::a_name_heard_once_survives_a_bridge_restart | '(you)' and the cards come later |
| people.names | behaviour | `ui/Peers.kt:displayName` | `messages.py:name_of` | both | verified | h_names::a_name_heard_once_survives_a_bridge_restart |  |
| people.empty | strings | `ui/screens/PeersScreen.kt:155-165` | `people.py:update` | both | built |  |  |
| people.cards | card | `ui/screens/ContactCards.kt` | `` | both | missing |  | 0.11.0 |
| people.sheet | sheet | `ui/components/NodeDetailSheet.kt` | `__main__.py:node_sheet` | both | partial |  | the signal words and the sheet's layout come with 0.12.0 |
| setup | screen | `ui/screens/SetupScreen.kt` | `setup.py:SetupScreen` | both | built |  |  |
| setup.node | screen | `ui/screens/SettingsScreen.kt:384-525` | `setup.py:NodeScreen` | both | built |  | the Bluetooth card as Android's; the cover card and the device card are this edition's |
| setup.node.cover | linux-only | `-` | `setup.py:NodeScreen.update_cover` | cover | built |  | the PinePhone's LoRa back cover as the node |
| setup.node.pin | linux-only | `-` | `setup.py:NodeScreen.ask_pin` | bluetooth | built |  | Android's system shows the PIN dialog; here the app does |
| setup.node.device | linux-only | `-` | `setup.py:NodeScreen` | both | built |  | which node this device has, and the look-again button |
| setup.satellite | screen | `ui/screens/SettingsScreen.kt:529-735` | `setup.py:SatelliteScreen` | both | partial |  | the node's modem section and the 9704 card come with 0.12.0 |
| setup.satellite.mailbox | dialog | `ui/components/CheckMailboxButton.kt` | `setup.py:SatelliteScreen.check_mailbox` | both | partial |  | the confirmation comes with 0.12.0 |
| passes | screen | `ui/screens/PassPredictorScreen.kt` | `passes.py:PassesScreen` | both | built |  |  |
| passes.position | linux-only | `-` | `passes.py:PositionDialog` | both | built |  | a position typed in, for a phone without a fix |
| setup.hub | screen | `ui/screens/SettingsScreen.kt:1625-1900` | `setup.py:HubScreen` | both | partial |  | the six states, the form and 'Reach a kit' come with 0.9.1 |
| setup.hub.provision | dialog | `ui/components/ProvisionLinkDialog.kt` | `` | both | missing |  | 0.11.0 |
| setup.hub.key-changed | dialog | `ui/screens/SettingsScreen.kt:222-256` | `` | both | missing |  | 0.9.1 |
| setup.sms | screen | `ui/screens/SettingsScreen.kt:sms` | `setup.py:SmsScreen` | both | partial |  | 'Where a text goes with no recipient' comes with 0.9.1 |
| setup.safety | screen | `ui/screens/SosScreens.kt:SafetyScreen` | `setup.py:SafetyScreen` | both | partial |  | the alarm test and Android's words for the check-in timer come with 0.6.0 |
| setup.safety.contacts | card | `ui/screens/SosScreens.kt:contacts` | `setup.py:SafetyScreen` | both | partial |  | 'Choose from your contacts' comes with 0.11.0 |
| setup.safety.checkin | card | `ui/screens/SettingsScreen.kt:992-1061` | `setup.py:SafetyScreen` | both | partial |  | Android's words and the triggered state come with 0.6.0 |
| sos | screen | `ui/screens/SosScreens.kt:SosScreen` | `` | both | missing |  | 0.6.0 |
| sos.test | dialog | `ui/screens/SosScreens.kt:424-450` | `` | both | missing |  | 0.6.0 |
| geofence | screen | `ui/screens/GeofenceScreen.kt` | `` | both | missing |  | 0.10.0 |
| setup.messaging | screen | `ui/screens/SettingsScreen.kt:messaging` | `setup.py:MessagingScreen` | both | partial |  | read only until 0.9.1 |
| setup.maps | screen | `ui/screens/SettingsScreen.kt:maps` | `setup.py:MapsScreen` | both | partial |  | 0.10.0 |
| setup.integrations | screen | `ui/screens/SettingsScreen.kt:integrations` | `setup.py:IntegrationsScreen` | both | partial |  | read only until 0.9.1 |
| radio-config | screen | `ui/screens/RadioConfigScreen.kt` | `setup.py:RadioScreen` | both | partial |  | read only until 0.9.0 (Bridge change B1) |
| setup.advanced | screen | `ui/screens/SetupScreen.kt:162-170` | `setup.py:AdvancedScreen` | both | built |  | the rows; the pages behind them are a web view until 0.7.0 and 0.8.0 |
| rules | screen | `ui/screens/RulesScreen.kt` | `` | both | missing |  | 0.7.0 |
| interfaces | screen | `ui/screens/InterfacesScreen.kt` | `` | both | missing |  | 0.7.0 |
| deliveries | screen | `ui/screens/DeliveryScreen.kt` | `` | both | missing |  | 0.7.0 |
| topology | screen | `ui/screens/TopologyScreen.kt` | `` | both | missing |  | 0.8.0 |
| audit | screen | `ui/screens/AuditScreen.kt` | `` | both | missing |  | 0.8.0 |
| credentials | screen | `ui/screens/CredentialsScreen.kt` | `` | both | missing |  | 0.8.0 |
| decrypt | screen | `ui/screens/DecryptScreen.kt` | `` | both | missing |  | 0.8.0 |
| setup.diagnostics | screen | `ui/screens/SettingsScreen.kt:2226-2311` | `` | both | missing |  | 0.8.0 |
| nodelog | screen | `ui/screens/NodeLogScreen.kt` | `setup.py:NodeLogScreen` | cover | partial |  | the daemon's journal; Pause, Clear, Share and the Bluetooth node's log come with 0.8.0 |
| about | screen | `ui/screens/AboutScreen.kt` | `setup.py:AboutScreen` | both | partial |  | Android's sections come with 0.12.0 |
| welcome | screen | `ui/screens/Onboarding.kt:90-149` | `` | both | missing |  | 0.12.0 |
| notification.message | notification | `GatewayService message notifications` | `notify.py` | both | verified | h_notify::one_notification_per_text_in_android_words |  |
| notification.quiet-in-front | behaviour | `GatewayService` | `notify.py:app_in_front` | both | verified | h_notify::no_notification_while_the_app_is_in_front |  |
| notification.sos | notification | `sos/SosController.kt` | `notify.py` | both | verified | h_notify::sos_notification_offers_cancel |  |
| notification.failure | notification | `GatewayService delivery failures` | `notify.py` | both | built |  |  |
| notification.signal | notification | `GatewayService satellite signal` | `notify.py` | both | built |  | drawn from a stand-in status on the bench |
| outside.tile | linux-only | `-` | `phosh-plugins/meshsat-quick-setting.c` | both | built |  | Phosh's quick settings, for Android's status-bar icon |
| outside.lockscreen | linux-only | `-` | `phosh-plugins/meshsat-lockscreen.c` | both | built |  | not yet seen on the lock screen itself |
| outside.tray | linux-only | `-` | `notify.py:tray` | both | built |  | not yet tried on a desktop |
| watchdog.banner | linux-only | `-` | `__main__.py:on_state` | cover | built |  | the radio in the cover stopped answering |
| excluded.permissions | behaviour | `ui/components/PermissionAsk.kt` | `-` | both | excluded |  | Android's runtime permissions have no counterpart; the welcome screen names what Linux asks instead (geoclue, Bluetooth) |
| excluded.play-edition | behaviour | `sms/SmsCapability.kt` | `-` | both | excluded |  | the Google Play edition switch: there is one edition here |
| excluded.gateway-notification | notification | `GatewayService foreground notification` | `-` | both | excluded |  | the Bridge is a system service; it needs no persistent notification to stay alive |
| excluded.boot-receiver | behaviour | `BootReceiver, LocalApiServer` | `-` | both | excluded |  | the Bridge's units start with the device; its API is the Bridge's own |
| excluded.transforms | behaviour | `transform pipeline` | `-` | both | excluded |  | the Bridge's per-interface transforms do that job |
| excluded.all-settings | screen | `ui/screens/SettingsScreen.kt:all` | `-` | both | excluded |  | unreachable in Android's own navigation |
| excluded.spp-9704 | card | `iridium/Iridium9704 over HC-05` | `-` | both | excluded |  | classic Bluetooth SPP is Android's path to the 9704; here it is a USB card with its own words |
| excluded.share-sheet | behaviour | `Share intents` | `-` | both | excluded |  | saved to a file instead |
| blocked.sms-live | behaviour | `sms/` | `setup.py:SmsScreen, messages.py` | both | blocked |  | a SIM in the bench phone |
| blocked.satellite-live | behaviour | `iridium/` | `setup.py:SatelliteScreen` | both | blocked |  | a RockBLOCK on USB-C, or the T-Beam with one in Bluetooth range |

## Words, per Android file

| file | carried | excluded | missing |
|---|---|---|---|
| `ui/screens/SettingsScreen.kt` | 23/251 | 0 | 228 |
| `ui/screens/RadioConfigScreen.kt` | 25/146 | 0 | 121 |
| `ui/screens/RulesScreen.kt` | 3/83 | 0 | 80 |
| `ui/screens/DeliveryScreen.kt` | 7/69 | 0 | 62 |
| `ui/screens/InterfacesScreen.kt` | 6/59 | 0 | 53 |
| `ui/screens/MessagesScreen.kt` | 32/73 | 0 | 41 |
| `ui/screens/AuditScreen.kt` | 5/43 | 0 | 38 |
| `ui/screens/SosScreens.kt` | 36/72 | 0 | 36 |
| `ui/screens/GeofenceScreen.kt` | 12/46 | 0 | 34 |
| `ui/screens/ContactCards.kt` | 12/34 | 0 | 22 |
| `ui/screens/TopologyScreen.kt` | 7/29 | 0 | 22 |
| `sos/SosController.kt` | 7/26 | 0 | 19 |
| `ui/screens/AboutScreen.kt` | 15/32 | 0 | 17 |
| `ui/screens/Onboarding.kt` | 11/27 | 0 | 16 |
| `ui/components/ProvisionClaimHost.kt` | 1/17 | 0 | 16 |
| `ui/screens/MapScreen.kt` | 15/30 | 0 | 15 |
| `ui/components/CheckMailboxButton.kt` | 3/18 | 0 | 15 |
| `ui/screens/CredentialsScreen.kt` | 1/15 | 0 | 14 |
| `ui/screens/DashboardScreen.kt` | 18/31 | 0 | 13 |
| `ui/screens/NodeLogScreen.kt` | 0/13 | 0 | 13 |
| `sos/SosRun.kt` | 3/16 | 0 | 13 |
| `ui/screens/DecryptScreen.kt` | 3/14 | 0 | 11 |
| `ui/components/NodeDetailSheet.kt` | 8/16 | 0 | 8 |
| `ui/components/ProvisionLinkDialog.kt` | 1/9 | 0 | 8 |
| `ui/screens/PassPredictorScreen.kt` | 32/39 | 0 | 7 |
| `ui/components/RegionCheck.kt` | 0/5 | 0 | 5 |
| `ui/screens/HomeLanes.kt` | 33/37 | 0 | 4 |
| `ui/screens/SetupScreen.kt` | 51/55 | 0 | 4 |
| `ui/components/PermissionAsk.kt` | 0/4 | 0 | 4 |
| `sos/SosMessages.kt` | 8/11 | 0 | 3 |
| `ui/components/Lane.kt` | 1/3 | 0 | 2 |
| `ui/components/MapChrome.kt` | 1/3 | 0 | 2 |
| `ui/components/NodeLinkBanner.kt` | 5/7 | 0 | 2 |
| `ui/Peers.kt` | 5/6 | 0 | 1 |
| `ui/components/Chrome.kt` | 0/1 | 0 | 1 |
| `ui/components/HoldToSend.kt` | 0/1 | 0 | 1 |
| `ui/MeshSatUI.kt` | 23/23 | 0 | 0 |
| `ui/Words.kt` | 26/26 | 0 | 0 |
| `ui/screens/PeersScreen.kt` | 13/13 | 0 | 0 |
| `ui/components/SkyChart.kt` | 7/7 | 0 | 0 |
