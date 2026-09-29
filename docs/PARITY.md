# Parity with MeshSat Android

MeshSat Android is the reference, pinned at `v2.19.4`. One row per screen, tab, card, dialog, banner and notification of the Android app; a row is done when the Linux app has it, in Android's words, and a test proves it. Kept by `tools/parity-check.py` from `tests/parity/ledger.json`; the words by `tools/android-strings.py`.

**Rows:** 136: 10 missing, 11 partial, 19 built, 85 verified, 9 excluded, 2 blocked.

**Words:** 1040 of 1410 readable strings of Android's `ui/` and `sos/` are in the Linux sources, 2 excluded with a reason, 368 still to port.

States: `missing` (not there), `partial` (some of it), `built` (there, untested), `verified` (there, in Android's words, with a test that ran green on the phone), `excluded` (not ported, with the reason), `blocked` (built and tested against the scripted Bridge, waiting for hardware the bench lacks).

| id | kind | Android | Linux | modes | state | test | note |
|---|---|---|---|---|---|---|---|
| shell.strip | banner | `ui/MeshSatUI.kt:330-352` | `widgets.py:StatusStrip` | both | verified | h_home::sentence_and_lanes_follow_the_bridge | the five items with Android's descriptions |
| shell.navbar | banner | `ui/MeshSatUI.kt:Tab` | `widgets.py:NavBar` | both | verified | h_shell::every_route_opens_and_fits_the_screen |  |
| shell.banner.node | banner | `ui/components/NodeLinkBanner.kt` | `__main__.py:on_state` | both | built |  | the 'Bluetooth is off' state waits for Bridge change B13 |
| shell.banner.sos | banner | `ui/screens/SosScreens.kt` | `__main__.py:on_state` | both | verified | h_sos::sos_screen_shows_where_it_went_and_the_cancellation | SOS and alarm test words |
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
| home.sos-card | card | `ui/screens/SosScreens.kt:SosCard` | `home.py:HomeScreen.update_sos_card` | both | verified | h_sos::alarm_test_goes_route_by_route_and_settles |  |
| home.sos.hold | behaviour | `ui/components/HoldToSend.kt` | `widgets.py:HoldButton` | both | verified | h_home::sos_hold_bar_asks_before_sending_when_activated_by_name | the accessible activation asks first, as Android's |
| home.sos.send-dialog | dialog | `ui/screens/SosScreens.kt:389-399` | `home.py:sos_activate` | both | verified | h_home::sos_hold_bar_asks_before_sending_when_activated_by_name |  |
| home.sos.cancel-dialog | dialog | `ui/screens/SosScreens.kt:403-411` | `home.py:sos_cancel_asked` | both | verified | h_home::sos_confirmed_activates_and_can_be_cancelled |  |
| home.signal-history | card | `ui/screens/DashboardScreen.kt:signal` | `home.py:draw_chart` | both | built |  |  |
| home.recent | card | `ui/screens/DashboardScreen.kt:recent` | `home.py:update` | both | built |  |  |
| home.arrange | dialog | `ui/screens/DashboardScreen.kt:ReorderDialog` | `` | both | missing |  | 0.12.0 |
| home.card.mailbox | card | `ui/screens/DashboardScreen.kt:229-260` | `` | both | missing |  | 0.12.0 |
| home.card.position | card | `ui/screens/DashboardScreen.kt:275-310` | `` | both | missing |  | 0.12.0 |
| home.card.charts | card | `ui/screens/DashboardScreen.kt:311-372` | `` | both | missing |  | 0.12.0 |
| messages | screen | `ui/screens/MessagesScreen.kt` | `messages.py:MessagesScreen` | both | verified | h_messages::search_filters_all_messages | search and the MessageCard rows of All Messages since 0.7.0 |
| messages.new-message | dialog | `ui/screens/MessagesScreen.kt:NewMessageDialog` | `messages.py:new_message` | both | verified | h_messages::new_message_to_a_node_opens_that_node |  |
| messages.search | behaviour | `ui/screens/MessagesScreen.kt:308-331` | `messages.py:MessagesScreen.query_changed` | both | verified | h_messages::search_filters_all_messages | in All Messages only, as Android; the rows are Android's MessageCard |
| chat | screen | `ui/screens/MessagesScreen.kt:ChatScreen` | `messages.py:ChatScreen` | both | verified | h_chat::own_bubbles_carry_a_delivery_mark | the bubble audit (MESHSAT-1399), measured on the bench phone's captures (720x1440, scale 2; 1 dp = 0.9 px): Android's ChatBubble is 80 % of the column, 10 dp inside, a 20 dp header (the transport in labelSmall, the time, the delivery mark, a 20 dp copy button with a 12 dp icon), the text in bodyMedium 4 dp below, 4 dp between bubbles, one line 64 dp tall. 0.6.0 drew a bubble at least 220 dp wide, 12 dp inside, a 40 dp header (the copy button's 12 dp padding) and the text in bodyLarge: one line 180 px (100 dp) tall, 12 dp apart. 0.7.0: 532 of 662 px wide (80 %), one line 114 px (63 dp) tall, 4 dp apart; the header inside the screen's 16 dp padding without a divider, the subtitle in bodySmall, the open lock muted ("Encryption key"); per-chat keys come with 0.12.0 |
| chat.send | behaviour | `ui/screens/MessagesScreen.kt:send` | `messages.py:ChatScreen.send` | both | verified | h_chat::send_posts_once_and_shows_the_bubble |  |
| chat.failed-send | behaviour | `ui/screens/MessagesScreen.kt:send` | `messages.py:ChatScreen.send` | both | verified | h_chat::a_failed_send_keeps_the_text_and_says_why |  |
| chat.composer-words | strings | `ui/screens/MessagesScreen.kt:586-647` | `model/chat.py` | both | verified | h_chat::the_composer_says_how_the_message_goes | the four placeholders, the six footer lines, the bytes and credits, the 340-byte limit that disables Send; the node-down toast (h_chat::the_mesh_down_refuses_the_send) |
| chat.ticks | behaviour | `ui/screens/MessagesScreen.kt:DeliveryMark` | `messages.py:ChatScreen.bubble` | both | verified | h_chat::own_bubbles_carry_a_delivery_mark | a clock, one check, a question mark, a red mark, two checks; from the Bridge's delivery_status; the Hub's receipt and the carrier's report are not in the Bridge's feed yet (one check for them) |
| chat.key | sheet | `ui/screens/SettingsScreen.kt:KeyManagementSection` | `` | both | missing |  | 0.12.0 |
| map | screen | `ui/screens/MapScreen.kt:345-415` | `mapview.py:MapScreen, mapwidget.py:MeshMap` | both | verified | h_tracks::a_the_map_and_its_panel | one map for the app's life, as Android's (layers, hidden nodes and camera kept); the camera rules (the first node positions fit everyone once, before them the phone's first fix at 14); Centre on me (the phone layer on, zoom max(current, 15)), Show everyone (showPoints), the three toasts; the markers drawn above the dark filter: sand diamonds 22 dp faded after 15 min with their names on a pill, this phone an 18 dp orange dot with its accuracy circle; bubbles on markers and tracks (osmdroid's info window: title and snippet), a marker tap pans to it. In cover mode the node that is the phone's own radio is the orange dot, not a diamond; a node over Bluetooth is a device of its own and a diamond |
| map.chrome | card | `ui/components/MapChrome.kt:107-194` | `mapwidget.py:MeshMap` | both | verified | h_maps::f_offline_the_detailed_map_serves | the round 48 dp buttons (Zoom in, Zoom out and the screen's own), the note in the corner: the OpenStreetMap credit online, 'Offline map: <name>. Outside it, the world overview.' or the world overview's sentence offline; offline after three failed downloads in a row, back with one that works (shared by both maps); the Map tab zooms out to 5 offline with only the world overview |
| map.panel | card | `ui/screens/MapScreen.kt:418-620` | `mapview.py:MapScreen.fill_panel` | both | verified | h_tracks::b_a_hidden_node_loses_marker_and_track | Layers and nodes: the summary, the three layers with their dots, this phone's row with its accuracy, Show all and Hide all, the node rows newest first (a check box hides the marker and the track; the row centres the map on the node at zoom max(current, 14)); the list at most half the map area's height; the hidden nodes are kept, so a node heard later shows |
| map.tracks | behaviour | `map/MapTracks.kt, ui/screens/MapScreen.kt:101-233` | `model/tracks.py:group, mapview.py` | both | verified | h_tracks::a_the_map_and_its_panel | the positions of the last 24 hours from the Bridge (GET /api/positions, 5,000 newest, all nodes together), re-read every 30 s while on view; a dashed sand line per node (75 %, 3 dp, 8 on 5 off, round caps), joined to its marker, two points at least; 'Track of <name>'; stations only the position log knows (APRS, TAK) are markers and tracks too |
| people | screen | `ui/screens/PeersScreen.kt` | `people.py:PeopleScreen` | both | partial | h_names::a_name_heard_once_survives_a_bridge_restart | '(you)' and the cards come later |
| people.names | behaviour | `ui/Peers.kt:displayName` | `messages.py:name_of` | both | verified | h_names::a_name_heard_once_survives_a_bridge_restart |  |
| people.empty | strings | `ui/screens/PeersScreen.kt:155-165` | `people.py:update` | both | built |  |  |
| people.cards | card | `ui/screens/ContactCards.kt` | `` | both | missing |  | 0.11.0 |
| people.sheet | sheet | `ui/components/NodeDetailSheet.kt` | `__main__.py:node_sheet, model/nodes.py` | both | verified | h_tracks::g_the_node_sheet_and_show_on_map | the title (' (your node)'), the short name and id two spaces apart, the rows with their 96 dp labels (Last heard and Signal not for your own node, Hardware when known, Position '%.5f, %.5f, ago' or 'Not shared yet...'), Message (not for your own node) and Show on map (only with a position); the signal words from the node list (the Bridge keeps no last-packet signal per node: 'as your node last measured it'); battery: the Bridge's 0 is Android's -1, 'Not reported' |
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
| setup.sms | screen | `ui/screens/SettingsScreen.kt:1903-1981` | `setup.py:SmsScreen` | both | verified | h_messaging::no_recipient_number_goes_over_the_sms_gateway | Text messages (the SIM through the Bridge, ModemManager) and Where a text goes with no recipient |
| setup.safety | screen | `ui/screens/SosScreens.kt:SafetyScreen` | `pages/safety.py:SafetyScreen` | both | verified | h_sos::safety_page_contacts_and_check_in_timer |  |
| setup.safety.contacts | card | `ui/screens/SosScreens.kt:contacts` | `pages/safety.py:SafetyScreen` | both | partial | h_sos::safety_page_contacts_and_check_in_timer | typed numbers as Android's; 'Choose from your contacts' (the address book) comes with 0.11.0 |
| setup.safety.checkin | card | `ui/screens/SettingsScreen.kt:992-1061` | `pages/safety.py:SafetyScreen` | both | verified | h_sos::safety_page_contacts_and_check_in_timer |  |
| sos | screen | `ui/screens/SosScreens.kt:SosScreen` | `pages/sos.py:SosScreen` | both | verified | h_sos::sos_screen_shows_where_it_went_and_the_cancellation |  |
| sos.test | dialog | `ui/screens/SosScreens.kt:424-450` | `sosflow.py:Flow.start, model/sosrun.py` | both | verified | h_sos::alarm_test_goes_route_by_route_and_settles | the mesh leg heard by the T-Deck on the bench (l_alarm) |
| geofence | screen | `ui/screens/GeofenceScreen.kt` | `pages/zones.py:ZonesScreen` | both | verified | h_zones::a_the_list_in_androids_words | the map over the top half (long press to place or move, Centre on me, the zones in amber, the nodes, this phone), the list or the editor under it; the zones live in the Bridge (MESHSAT-1414: every mesh position checked, the crossings kept in memory until it restarts, as Android's service), read every 5 s; the alerts go nowhere but this list, as on Android |
| setup.messaging | screen | `ui/screens/SettingsScreen.kt:736-983, 1134-1177` | `pages/messaging.py:MessagingScreen` | both | verified | h_messaging::the_three_cards_in_androids_words | the settings live in the Bridge's link chains (PUT /api/interfaces/{id}/transforms, MESHSAT-1412); the app's preferences keep what the chains cannot (the key while encryption is off) |
| setup.maps | screen | `ui/screens/SettingsScreen.kt:1984-2223` | `pages/maps.py:MapsScreen` | both | verified | h_maps::b_a_map_added_is_in_use | Offline maps: the world overview always there (Android's own world.mbtiles, byte for byte), the detailed maps with their size and zooms, In use, the vector line, Use my detailed map (keeps its file), Add a detailed map (the copy is checked before it replaces a map of the same name, where Android overwrote first; a file named world.mbtiles keeps a name of its own), the three add toasts |
| setup.integrations | screen | `ui/screens/SettingsScreen.kt:integrations` | `setup.py:IntegrationsScreen` | both | partial |  | read only until 0.9.1 |
| radio-config | screen | `ui/screens/RadioConfigScreen.kt` | `pages/radio.py:RadioConfigScreen` | both | verified | h_radio::name_tab_facts_and_save | seven tabs over the Bridge's named settings (GET /api/config?format=names, MESHSAT-1405); every Apply sends only what changed and the Bridge lays it over the node's own section; a tab is drawn again only when its settings change, so a poll keeps what is typed (remember(loaded)) |
| setup.advanced | screen | `ui/screens/SetupScreen.kt:162-170` | `setup.py:AdvancedScreen` | both | verified | h_shell::every_route_opens_and_fits_the_screen | every row a native page since 0.8.0; the Diagnostics row reads "Link health, service" (no batch queue, no local crash telemetry here) |
| rules | screen | `ui/screens/RulesScreen.kt` | `pages/rules.py:RulesScreen` | both | verified | h_rules::tabs_badges_and_cards | five tabs with badges, subtitles and empty texts; the cards with the switch, the route in the links' colours, the meta line, the filters; the add button |
| interfaces | screen | `ui/screens/InterfacesScreen.kt` | `pages/links.py:LinksScreen` | both | verified | h_links::six_tabs_in_androids_words | a link the Bridge's device manager does not bind (the mesh over the daemon or Bluetooth, the SIM, the Hub) shows the lane's state the app sees |
| deliveries | screen | `ui/screens/DeliveryScreen.kt` | `pages/deliveries.py:DeliveryScreen` | both | verified | h_queue::counts_chips_and_cards | the counts by state, a chip per link, the cards, the empty texts |
| topology | screen | `ui/screens/TopologyScreen.kt` | `pages/topology.py:TopologyScreen` | both | verified | h_advanced::topology_is_what_was_heard | links only from NeighborInfo reports (/api/neighbors) and nodes heard 0 hops away (/api/nodes), never inferred; the force layout of 90 steps; pinch and drag are GTK gestures (a finger proves them, not the suite); numbers rounded half up as Kotlin writes them |
| audit | screen | `ui/screens/AuditScreen.kt` | `pages/audit.py:AuditScreen` | both | verified | h_advanced::audit_counts_filters_checks_and_saves | count, signing key, a chip per link, the check and its words, Save a copy (the whole log, page by page: Bridge MESHSAT-1402), Show older entries; the saved copy's hash chain checks against a real Bridge (s_advanced::a_passed_on_text_is_an_audit_entry_the_copy_can_check) |
| credentials | screen | `ui/screens/CredentialsScreen.kt` | `pages/credentials.py:CredentialsScreen` | both | verified | h_advanced::credentials_cards_import_and_delete | the Bridge's credential store; Import PEM through the file dialog; a real certificate's subject, SHA-256 and expiry as the Bridge stores them (s_advanced::a_certificate_is_the_one_the_bridge_stores) |
| decrypt | screen | `ui/screens/DecryptScreen.kt` | `pages/decrypt.py:DecryptScreen` | both | verified | h_advanced::decrypt_with_the_links_key | AES-256-GCM (python3-cryptography), the key from the Bridge's encrypt transform (the key Setup > Messaging saves, 0.9.1); a vector made with the Bridge's own construction opens (AesGcmWireFormatTest.test_a_text_the_bridge_encrypted_opens) |
| setup.diagnostics | screen | `ui/screens/SettingsScreen.kt:1069-1130, 2226-2311` | `pages/diagnostics.py:DiagnosticsScreen` | both | verified | h_advanced::diagnostics_health_and_the_service | Link health and Background service; the restart and the boot switch through polkit (dry under test); "Start after a phone restart" keeps Android's first sentence only (its second is about Android); Crash reports excluded (row setup.diagnostics.telemetry) |
| nodelog | screen | `ui/screens/NodeLogScreen.kt` | `pages/nodelog.py:NodeLogScreen` | cover | verified | h_advanced::node_log_follows_pauses_clears_and_shares | cover mode: the daemon's journal followed (the package adds the phone's people to systemd-journal), lines as NodeLog.format, 2000 kept, Pause/Resume, Clear, Share = copy and save (the share sheet is the approved exclusion); the Bluetooth node's log: row nodelog.bluetooth |
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
| notification.alarm-test | notification | `sos/SosController.kt:notify` | `__main__.py:on_sos_change` | both | built |  | 'Alarm test running' with Stop test, posted by the app itself |
| sos.words | strings | `sos/SosMessages.kt` | `sos.py` | both | verified | SosMessagesTest.test_a_test_and_a_cancellation_never_raise_an_alarm_whatever_the_name | SosMessagesTest ported |
| sos.run | behaviour | `sos/SosRun.kt, SosProgress` | `model/sosrun.py, sosflow.py` | both | verified | FlowTest.test_a_test_goes_route_by_route_and_tells_the_hub | the Bridge carries the mesh, satellite and Hub legs of a real SOS; the app the SMS legs and the test |
| deliveries.details | dialog | `ui/screens/DeliveryScreen.kt:DeliveryDetailsDialog` | `pages/deliveries.py:open_details` | both | verified | h_queue::details_dialog_shows_the_facts_and_the_raw_fields | the facts, the text, Show details, Retry / Cancel message / Close |
| deliveries.confirm | dialog | `ui/screens/DeliveryScreen.kt:ConfirmQueueRequestDialog` | `pages/deliveries.py:ask` | both | verified | h_queue::cancel_and_retry_are_confirmed_and_reach_the_bridge | the satellite credit, the SMS carrier and the plain retry questions; the cancel question; the toasts; s_queue::cancel_and_retry_follow_the_bridges_state against the real Bridge |
| deliveries.words | strings | `ui/screens/DeliveryScreen.kt:96-171` | `model/deliveries.py` | both | verified | DeliveryProblemTextTest.test_a_radio_out_of_reach_is_not_described_as_waiting_for_a_satellite | DeliveryProblemTextTest ported; the states, urgencies, guarantees, confirmations, tries |
| interfaces.tabs | tab | `ui/screens/InterfacesScreen.kt:IfaceTab` | `pages/links.py:render` | both | verified | h_links::six_tabs_in_androids_words | Links, Rules, Capabilities, Groups, Backup links, Health, with the badges; the capabilities are the Bridge's channel table |
| interfaces.switch-off | dialog | `ui/screens/InterfacesScreen.kt:210-245` | `pages/links.py:switch_changed` | both | verified | h_links::switch_off_asks_first | by design: every link gets Android's general sentence; Android's satellite sentence (the modem not used, nothing coming in) is not true of the Bridge, which keeps a switched-off modem connected and reads what comes in; a switched-off link stops its deliveries and holds its queue in the Bridge since MESHSAT-1401 (s_links::switch_off_and_on_persist against a real Bridge); Try to connect now binds the link's device |
| rules.editor | dialog | `ui/screens/RulesScreen.kt:AddEditRuleDialog` | `pages/rules.py:RuleEditor` | both | verified | h_rules::a_new_rule_writes_androids_record | every field, helper and error; the Hub duplicate warning; a save writes the rule itself with the editor's fields over it (h_rules::a_save_keeps_every_column_and_delete_asks_first; s_rules against the real Bridge) |
| rules.delete | dialog | `ui/screens/RulesScreen.kt:358-390` | `pages/rules.py:delete_asked` | both | verified | h_rules::a_save_keeps_every_column_and_delete_asks_first | what deleting changes, then You cannot undo this. |
| rules.queue | tab | `ui/screens/RulesScreen.kt:QueueTabContent` | `pages/rules.py:queue_tab` | both | verified | h_rules::the_queue_tab_cancels_and_retries | Waiting to go out (N) with Cancel, Did not go out (N) with Retry |
| rules.words | strings | `ui/screens/RulesScreen.kt:98-154, 402-413, 591-623, 711-764` | `model/rules.py` | both | verified | RuleLinkChoicesTest.test_a_switched_off_link_is_not_offered | RuleLinkChoicesTest and DuplicatesTheHubTest ported; the tabs, routes, filters, consequences, hidden settings, the record |
| topology.empty | behaviour | `ui/screens/TopologyScreen.kt:EmptyTopology` | `pages/topology.py:TopologyScreen.render` | both | verified | h_advanced::topology_without_reports_or_others | the empty mesh and the Neighbor Info notice |
| audit.check | behaviour | `ui/screens/AuditScreen.kt:357-395` | `model/audit.py:check_words` | both | verified | h_advanced::audit_a_changed_log_says_where | a changed log names the first changed entry by its number |
| decrypt.words | strings | `crypto/AesGcmCrypto.kt, AesGcmWireFormatTest` | `model/crypto.py` | both | verified | AesGcmWireFormatTest.test_encrypted_output_has_a_12_byte_nonce_and_a_16_byte_tag | AesGcmWireFormatTest ported |
| setup.diagnostics.telemetry | card | `ui/screens/SettingsScreen.kt:2226-2246` | `` | both | excluded |  | Android's local telemetry server (LocalApiServer, localhost:6051): the approved exclusion; the Bridge is a system service with its own journal |
| nodelog.bluetooth | behaviour | `ui/screens/NodeLogScreen.kt:63-129, ble/NodeLog.kt` | `pages/nodelog.py:read_bluetooth, set_streaming` | bluetooth | verified | h_radio_bt::the_node_log_streams_over_the_link | the switch writes only security.debug_log_api_enabled (the Bridge keeps the node's keys); the Bridge follows LogRadio while the page asks (MESHSAT-1406); live: l_radio::b_the_tdecks_log_streams_while_its_switch_is_on (T-Deck A's own lines); Android's "restarts once" kept, T-Deck 2.7.26 does not restart (MESHSAT-1409) |
| nodelog.words | strings | `ble/NodeLog.kt` | `model/nodelog.py` | both | verified | NodeLogTest.test_the_buffer_holds_while_paused_and_keeps_2000 | the line format, the levels, the buffer that holds while paused |
| radio-config.name | tab | `ui/screens/RadioConfigScreen.kt:231-320` | `pages/radio.py:draw_name` | both | verified | h_radio::name_tab_facts_and_save | This node (hardware by Android's table, else the protobuf name: Portduino), Save name; the Bridge sends the node's own is_licensed back |
| radio-config.radio | tab | `ui/screens/RadioConfigScreen.kt:326-564` | `pages/radio.py:draw_radio` | both | verified | h_radio::radio_tab_sends_only_the_hop_limit | region, preset with Details, power 0-30, hops 1-7, transmit; read back 2.5 s after Apply; live: l_radio::a_hop_limit_set_in_the_app_reaches_the_tdeck (T-Deck A over Bluetooth, 4 read over USB, 3 put back) |
| radio-config.region-check | banner | `ui/components/RegionCheck.kt` | `model/radio.py:region_warning` | both | verified | h_radio::region_is_checked_and_asked_first | the phone's country from the SIM, else the language settings' territory (Android: SIM, else Locale); country names as Android's English Locale gives them |
| radio-config.radio.confirm | dialog | `ui/screens/RadioConfigScreen.kt:544-563` | `pages/radio.py:draw_radio` | both | verified | h_radio::region_is_checked_and_asked_first | "Apply these radio settings?" with its two consequences |
| radio-config.cover-power | linux-only | `` | `model/radio.py:COVER_POWER` | cover | verified | h_radio::radio_tab_sends_only_the_hop_limit | the LoRa back cover's transmit power: 0 dBm, capped by its service (SX126X_MAX_POWER), with the reason; no field, and Android's "0 means the highest power" hint left out there |
| radio-config.channels | tab | `ui/screens/RadioConfigScreen.kt:570-801` | `pages/radio.py:draw_channels` | both | verified | h_radio::channels_edit_never_sends_a_key | every channel the node reports, the key in words (the Bridge never gives the key), the edit dialog (name 11, role, MQTT both ways), "Change channel N?"; a write never carries a key and the Bridge keeps the node's |
| radio-config.position | tab | `ui/screens/RadioConfigScreen.kt:807-894` | `pages/radio.py:draw_position` | both | verified | h_radio::position_tab | GPS on, Fixed position, Every (seconds), Smart sharing |
| radio-config.bluetooth | tab | `ui/screens/RadioConfigScreen.kt:900-1026` | `pages/radio.py:draw_bluetooth` | bluetooth | verified | h_radio_bt::turning_bluetooth_off_asks_first | pairing modes, the fixed PIN of 6 digits, "Turn off Bluetooth?"; with the back cover the node has no Bluetooth of its own and the tab says so (h_radio::the_cover_has_no_wifi_or_bluetooth) |
| radio-config.wifi | tab | `ui/screens/RadioConfigScreen.kt:1032-1126` | `pages/radio.py:draw_wifi` | bluetooth | verified | h_radio_bt::wifi_with_the_password_hidden | the password hidden until shown (Android's eye icons); with the back cover the phone's own network is the node's, and the tab says so |
| radio-config.admin | tab | `ui/screens/RadioConfigScreen.kt:1132-1298` | `pages/radio.py:draw_restart` | both | verified | h_radio::restart_and_reset_ask_first | Set the clock, Restart (with the delay), Switch off (when the node can), Forget heard nodes, Factory reset, each after Android's question (Bridge: set_clock, shutdown, nodedb_reset, MESHSAT-1405); with the back cover the restart question leaves out the satellite modem, which is on the phone's USB |
| radio-config.not-loaded | banner | `ui/screens/RadioConfigScreen.kt:142-164, 216-225` | `pages/radio.py:not_loaded` | both | verified | h_radio::not_connected_offers_the_node_page | not connected: the card and Connect your node (to the Node page); not loaded: Android's two sentences; against a real Bridge with no node: s_radio::without_a_node_nothing_is_written |
| radio-config.words | strings | `ui/screens/RadioConfigScreen.kt` | `model/radio.py` | both | verified | RadioTabTest.test_only_what_changed_is_sent | labels, limits, the changes each tab sends, the questions and the toasts; a refusal of the Bridge in Android's words (409, 503) or its own (400) |
| setup.messaging.encryption | card | `ui/screens/SettingsScreen.kt:736-894` | `pages/messaging.py (Encryption)` | both | verified | h_messaging::a_generated_key_becomes_the_sms_chains | as Android, the SMS link's: encrypt on send, an optional decrypt on receive (Auto-decrypt: a text from an ordinary phone is kept, not dropped); Show, Generate, Save, Copy, Paste; Share saves a file (the approved share-sheet exclusion); a key that is not 64 hex characters is refused before it goes (the Bridge refuses it too, and no longer sends plain text with it, MESHSAT-1411); the QR button comes with the scanner (0.11.0, row setup.messaging.scan) |
| setup.messaging.scan | behaviour | `ui/screens/SettingsScreen.kt:862-884` | `` | both | missing |  | Scan QR Code (Hub Key Sync): with the scanner in 0.11.0 |
| setup.messaging.compression | card | `ui/screens/SettingsScreen.kt:896-983` | `pages/messaging.py (Message compression)` | both | verified | h_messaging::compression_where_the_bridge_can_encode | SMS and Iridium SBD, Off or MSVQ-SC, the stages; MSVQ-SC offered only where the Bridge can encode (GET /api/transforms/capabilities; this phone has no encoder: the Linux sentence says so); Android's MQTT (Hub) row is not here: the Bridge's Hub link has no transform chain |
| setup.messaging.quick | card | `ui/screens/SettingsScreen.kt:1134-1177, codec/CannedCodebook.kt` | `pages/messaging.py (Quick messages), model/messaging.py:CODEBOOK` | both | verified | CannedCodebookTest.test_known_messages_match_expected_text | the 30 brevity codes (CannedCodebookTest ported); the Bridge now reads a received code as its words (MESHSAT-1412), so 'Auto-detected on receive' holds |
| setup.sms.no-recipient | card | `ui/screens/SettingsScreen.kt:1945-1981` | `setup.py:SmsScreen.save_number` | both | verified | h_messaging::no_recipient_number_goes_over_the_sms_gateway | the SMS gateway's default number (destination_numbers), written with the gateway's switch and masked secrets kept (MESHSAT-1412); empty = a text with no recipient is not sent, as Android; against a real Bridge: s_messaging::the_sms_gateway_without_a_default_number |
| map.focus | behaviour | `ui/components/MapFocus.kt, ui/screens/MapScreen.kt:306-320` | `__main__.py:show_on_map, mapview.py:MapScreen.focus` | both | verified | h_tracks::g_the_node_sheet_and_show_on_map | People's Show on map: the Map tab as the tab bar opens it, the node back on the map, the Nodes layer on, zoom max(current, 14); 'This node has not sent a position yet.' when there is none |
| geofence.editor | card | `ui/screens/GeofenceScreen.kt:557-668` | `pages/zones.py:ZonesScreen.build_editor` | both | verified | h_zones::b_a_long_press_places_a_zone_and_save_sends_it | New zone: the centre line, Name, the logarithmic slider (50 m to 5 km in 10, 25, 100 m steps) and the metres field (10 to 50,000, digits only) in step, 'About ... across.', Alert when a node, the note, Save zone and Cancel; the three errors at once; saved as Android's 32-vertex circle; the draft a 60-point geodesic circle in orange |
| geofence.delete | dialog | `ui/screens/GeofenceScreen.kt:528-554` | `pages/zones.py:ZonesScreen.ask_delete` | both | verified | h_zones::e_delete_asks_first | Delete <name>?, Delete zone (red), Keep it; the alerts stay |
| geofence.alerts | card | `ui/screens/GeofenceScreen.kt:494-523` | `pages/zones.py:ZonesScreen.fill_list` | both | verified | h_zones::f_a_node_crossing_is_listed | Recent alerts: the newest 20 of the Bridge's 50, '<who> entered|left <zone>, <ago>', the node's name when the radio knows one |
| setup.maps.delete | dialog | `ui/screens/SettingsScreen.kt:2189-2221` | `pages/maps.py:MapsScreen.ask_delete` | both | verified | h_maps::h_delete_asks_first | Delete this map?, Delete (red), Keep it; 'Map deleted: <name>' |

## Words, per Android file

| file | carried | excluded | missing |
|---|---|---|---|
| `ui/screens/SettingsScreen.kt` | 60/251 | 0 | 191 |
| `ui/screens/ContactCards.kt` | 12/34 | 0 | 22 |
| `ui/screens/AboutScreen.kt` | 16/32 | 0 | 16 |
| `ui/screens/Onboarding.kt` | 12/27 | 0 | 15 |
| `ui/components/CheckMailboxButton.kt` | 3/18 | 0 | 15 |
| `ui/screens/MessagesScreen.kt` | 59/73 | 0 | 14 |
| `ui/components/ProvisionClaimHost.kt` | 3/17 | 0 | 14 |
| `ui/screens/DashboardScreen.kt` | 19/31 | 0 | 12 |
| `sos/SosController.kt` | 17/26 | 0 | 9 |
| `ui/screens/PassPredictorScreen.kt` | 32/39 | 0 | 7 |
| `ui/screens/SosScreens.kt` | 65/72 | 0 | 7 |
| `ui/components/ProvisionLinkDialog.kt` | 2/9 | 0 | 7 |
| `ui/screens/TopologyScreen.kt` | 25/29 | 0 | 4 |
| `ui/components/NodeDetailSheet.kt` | 12/16 | 0 | 4 |
| `ui/components/PermissionAsk.kt` | 0/4 | 0 | 4 |
| `sos/SosRun.kt` | 12/16 | 0 | 4 |
| `ui/screens/HomeLanes.kt` | 34/37 | 0 | 3 |
| `sos/SosMessages.kt` | 8/11 | 0 | 3 |
| `ui/screens/AuditScreen.kt` | 41/43 | 0 | 2 |
| `ui/screens/InterfacesScreen.kt` | 57/59 | 0 | 2 |
| `ui/screens/MapScreen.kt` | 28/30 | 0 | 2 |
| `ui/screens/SetupScreen.kt` | 53/55 | 0 | 2 |
| `ui/Peers.kt` | 5/6 | 0 | 1 |
| `ui/screens/CredentialsScreen.kt` | 14/15 | 0 | 1 |
| `ui/screens/DecryptScreen.kt` | 13/14 | 0 | 1 |
| `ui/screens/DeliveryScreen.kt` | 68/69 | 0 | 1 |
| `ui/screens/GeofenceScreen.kt` | 45/46 | 0 | 1 |
| `ui/components/HoldToSend.kt` | 0/1 | 0 | 1 |
| `ui/components/Lane.kt` | 2/3 | 0 | 1 |
| `ui/components/NodeLinkBanner.kt` | 6/7 | 0 | 1 |
| `ui/components/RegionCheck.kt` | 4/5 | 0 | 1 |
| `ui/MeshSatUI.kt` | 23/23 | 0 | 0 |
| `ui/Words.kt` | 26/26 | 0 | 0 |
| `ui/screens/NodeLogScreen.kt` | 11/13 | 2 | 0 |
| `ui/screens/PeersScreen.kt` | 13/13 | 0 | 0 |
| `ui/screens/RadioConfigScreen.kt` | 146/146 | 0 | 0 |
| `ui/screens/RulesScreen.kt` | 83/83 | 0 | 0 |
| `ui/components/Chrome.kt` | 1/1 | 0 | 0 |
| `ui/components/MapChrome.kt` | 3/3 | 0 | 0 |
| `ui/components/SkyChart.kt` | 7/7 | 0 | 0 |
