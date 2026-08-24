"""
morse_trainer_v1_6.py - Morse Trainer v1.6
Headless SSH Terminal Interface for Open CW Keyer mk2 (K3NG).
Features multi-profile support, session-based progression, Head Copy mode, 
and spaced high-contrast rendering.
"""

import collections
import glob
import random
import re
import sys
import time
import select
import termios
import tty
from dataclasses import dataclass
from typing import Deque, Optional, Dict

import serial
import serial.tools.list_ports

from trainer_engine import ProfileManager, TokenMetric
from word_banks import ITU_MORSE_MAP, get_meaning


@dataclass
class ResponseLog:
    challenge: str
    response: str
    status: str
    latency_ms: float
    expected_dotrep: str


def find_serial_port() -> Optional[str]:
    for port in serial.tools.list_ports.comports():
        desc = (port.description or "").lower()
        hwid = (port.hwid or "").lower()
        if any(dev in desc or dev in hwid for dev in ["ftdi", "ch340", "cp210", "pico", "uart", "usb serial"]):
            return port.device

    linux_ports = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*"))
    if linux_ports:
        return linux_ports[0]

    mac_ports = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*"))
    if mac_ports:
        return mac_ports[0]

    return None


def get_dotrep(plain_text: str) -> str:
    """Formats Morse elements with explicit intra-element and inter-character spacing."""
    char_reps = []
    for char in plain_text:
        raw_morse = ITU_MORSE_MAP.get(char.upper(), "")
        if raw_morse:
            # Space out individual dits and dahs to avoid font ligature merging
            spaced_elements = " ".join(raw_morse)
            # Replace standard ascii with high-contrast bold unicode shapes
            spaced_elements = spaced_elements.replace(".", "●").replace("-", "━━")
            char_reps.append(spaced_elements)
    # 3 spaces between separate letters
    return "   ".join(char_reps)


def get_char_non_blocking(timeout: float) -> Optional[str]:
    """Reads a single keystroke from the terminal without requiring Enter."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        # cbreak allows Ctrl+C to trigger KeyboardInterrupt naturally
        tty.setcbreak(fd)
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if r:
            return sys.stdin.read(1)
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def flush_stdin():
    """Clears the input buffer to prevent bleed-over between challenges."""
    termios.tcflush(sys.stdin, termios.TCIFLUSH)


def strip_ansi(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s)


def pad_box_line(content: str, width: int = 66) -> str:
    vis_len = len(strip_ansi(content))
    pad_total = max(0, width - vis_len)
    left_pad = pad_total // 2
    right_pad = pad_total - left_pad
    return f"│{' ' * left_pad}{content}{' ' * right_pad}│"


class MorseTrainerCLI:
    def __init__(self):
        self.profile_mgr: Optional[ProfileManager] = None
        self.serial_conn: Optional[serial.Serial] = None
        self.running = True
        self.history: Deque[ResponseLog] = collections.deque(maxlen=3)
        self.session_metrics: Dict[str, TokenMetric] = collections.defaultdict(TokenMetric)

    def init_serial(self) -> bool:
        port_path = find_serial_port()
        if not port_path:
            return False
        try:
            self.serial_conn = serial.Serial(
                port=port_path,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            time.sleep(1.5)
            self.serial_conn.reset_input_buffer()
            return True
        except Exception:
            return False

    def read_paddle_response(self, challenge: str) -> str:
        if not self.serial_conn:
            return ""
        received = []
        expected_length = len(challenge)

        while True:
            if self.serial_conn.in_waiting:
                chunk = self.serial_conn.read(self.serial_conn.in_waiting).decode("ascii", errors="ignore")
                for char in chunk:
                    if char not in ["\r", "\n", " "]:
                        received.append(char.upper())
                
                if len(received) >= expected_length:
                    return "".join(received)
            time.sleep(0.01)

    def render_screen(
        self,
        challenge: str,
        feedback_state: Optional[str] = None,
        feedback_latency: float = 0.0,
        advance_msg: str = "",
        hide_challenge: bool = False,
        force_dotrep: bool = False
    ) -> None:
        state = self.profile_mgr.state
        show_dotrep = force_dotrep or self.profile_mgr.should_show_dotrep(challenge)
        dotrep = get_dotrep(challenge) if show_dotrep else "[Dotrep Hidden]"

        meaning = get_meaning(challenge)
        meaning_str = f"Meaning: {meaning}" if meaning else ""

        metric = self.session_metrics.get(challenge)
        acc_str = f"{metric.accuracy:.0f}%" if metric and metric.attempts > 0 else "--%"
        lat_str = f"{metric.avg_latency_ms:.0f}ms" if metric and metric.correct > 0 else "--ms"

        sys.stdout.write("\033[2J\033[H")
        print("=" * 68)
        print(" M7KQX MORSE TRAINER v1.6 | C. Webster (M7KQX) | www.m7kqx.co.uk")
        print(f" Profile: {self.profile_mgr.profile_name:<10} | Mode: {state.training_mode:<10} | WPM: {state.char_wpm}/{state.effective_wpm}")
        print("=" * 68)
        print("┌" + "─" * 66 + "┐")
        print("│  ACTIVE CHALLENGE:                                               │")
        print("│                                                                  │")

        if feedback_state == "OK":
            line1 = f"\033[1;92m✓  CORRECT ({feedback_latency:.0f} ms)\033[0m"
            print(pad_box_line(line1))
        elif feedback_state == "FAIL":
            line1 = f"\033[1;91m✗  INCORRECT  (Expected: {get_dotrep(challenge)})\033[0m"
            print(pad_box_line(line1))
        else:
            display_char = "???" if hide_challenge else challenge
            line1 = f"\033[1;96m{display_char}\033[0m      \033[1;33m{dotrep}\033[0m"
            print(pad_box_line(line1))

        if meaning_str and not feedback_state and not hide_challenge:
            print(pad_box_line(f"\033[37m{meaning_str}\033[0m"))
        else:
            print("│                                                                  │")

        print("│                                                                  │")
        print(f"│  Session Acc: {acc_str:<5}  Avg Latency: {lat_str:<7} Awaiting Input...        │")
        print("└" + "─" * 66 + "┘")

        if advance_msg:
            print(f"\033[1;92m >>> {advance_msg}\033[0m")
        else:
            print("")

        print(" RECENT RESPONSES:")
        if not self.history:
            print("  (No responses recorded yet this session)")
            print("  ---")
            print("  ---")
        else:
            for item in list(self.history):
                if item.status == "OK":
                    tag = "\033[92m[  OK  ]\033[0m"
                    detail = f"{item.latency_ms:.0f} ms"
                else:
                    tag = "\033[91m[ FAIL ]\033[0m"
                    detail = f"Got: '{item.response}' | Expected: {item.expected_dotrep}"

                print(f"  {tag} Challenge: \033[1m{item.challenge:<6}\033[0m | {detail}")

            for _ in range(3 - len(self.history)):
                print("  ---")

        print("-" * 68)
        print(" [Ctrl+C] Return to Main Menu")
        sys.stdout.flush()

    def update_session_metric(self, challenge: str, is_correct: bool, latency_ms: float) -> None:
        m = self.session_metrics[challenge]
        m.attempts += 1
        if is_correct:
            m.correct += 1
            m.total_latency_ms += latency_ms

    def run_head_copy_session(self) -> None:
        state = self.profile_mgr.state
        self.history.clear()
        self.session_metrics.clear()
        advance_msg = ""
        
        session_attempts = 0
        session_correct = 0

        try:
            while True:
                if state.session_length > 0 and session_attempts >= state.session_length:
                    break

                active_pool = self.profile_mgr.get_active_pool(state.training_mode)
                challenge = random.choice(active_pool)
                expected_dot = get_dotrep(challenge)

                self.render_screen(challenge, advance_msg=advance_msg, hide_challenge=True, force_dotrep=False)
                advance_msg = ""
                flush_stdin()

                if self.serial_conn:
                    self.serial_conn.reset_input_buffer()
                    self.serial_conn.write(challenge.encode('ascii'))

                t_start = time.perf_counter()
                
                t_elapsed = 0.0
                response_char = None
                while t_elapsed < 5.0:
                    response_char = get_char_non_blocking(0.1)
                    if response_char:
                        break
                    t_elapsed = time.perf_counter() - t_start

                latency_ms = (time.perf_counter() - t_start) * 1000.0
                session_attempts += 1

                if response_char and response_char.upper() == challenge:
                    session_correct += 1
                    self.profile_mgr.record_response(challenge, True, latency_ms)
                    self.update_session_metric(challenge, True, latency_ms)
                    self.history.appendleft(ResponseLog(challenge, response_char.upper(), "OK", latency_ms, expected_dot))
                    self.render_screen(challenge, feedback_state="OK", feedback_latency=latency_ms)
                    time.sleep(0.8)
                else:
                    self.profile_mgr.record_response(challenge, False, latency_ms)
                    self.update_session_metric(challenge, False, latency_ms)
                    actual_resp = response_char.upper() if response_char else "TIMEOUT"
                    self.history.appendleft(ResponseLog(challenge, actual_resp, "FAIL", latency_ms, expected_dot))

                    self.render_screen(challenge, advance_msg=advance_msg, hide_challenge=True, force_dotrep=True)
                    t_start_p2 = time.perf_counter()
                    p2_elapsed = 0.0
                    p2_response = None
                    while p2_elapsed < 3.0:
                        p2_response = get_char_non_blocking(0.1)
                        if p2_response and p2_response.upper() == challenge:
                            break
                        p2_elapsed = time.perf_counter() - t_start_p2
                    
                    if p2_response and p2_response.upper() == challenge:
                        pass
                    else:
                        self.render_screen(challenge, advance_msg=advance_msg, hide_challenge=False, force_dotrep=True)
                        flush_stdin()
                        time.sleep(3.0)
                        flush_stdin()

                unlocked = self.profile_mgr.evaluate_advancement(state.training_mode, self.session_metrics)
                if unlocked:
                    advance_msg = f"UNLOCKED: {unlocked}"

        except KeyboardInterrupt:
            time.sleep(0.4)

    def run_training_session(self) -> None:
        state = self.profile_mgr.state
        self.history.clear()
        self.session_metrics.clear()
        advance_msg = ""
        
        session_attempts = 0
        session_correct = 0

        try:
            while True:
                if state.session_length > 0 and session_attempts >= state.session_length:
                    break

                active_pool = self.profile_mgr.get_active_pool(state.training_mode)
                challenge = random.choice(active_pool)
                expected_dot = get_dotrep(challenge)

                self.render_screen(challenge, feedback_state=None, advance_msg=advance_msg)
                advance_msg = ""

                if self.serial_conn:
                    self.serial_conn.reset_input_buffer()

                t_start = time.perf_counter()
                
                response = self.read_paddle_response(challenge)
                latency_ms = (time.perf_counter() - t_start) * 1000.0

                session_attempts += 1

                if response == challenge:
                    session_correct += 1
                    self.profile_mgr.record_response(challenge, True, latency_ms)
                    self.update_session_metric(challenge, True, latency_ms)
                    self.history.appendleft(ResponseLog(challenge, response, "OK", latency_ms, expected_dot))
                    self.render_screen(challenge, feedback_state="OK", feedback_latency=latency_ms)
                else:
                    self.profile_mgr.record_response(challenge, False, latency_ms)
                    self.update_session_metric(challenge, False, latency_ms)
                    self.history.appendleft(ResponseLog(challenge, response, "FAIL", latency_ms, expected_dot))
                    self.render_screen(challenge, feedback_state="FAIL", feedback_latency=latency_ms)

                time.sleep(0.8)

                if state.training_mode != "WEAK":
                    unlocked = self.profile_mgr.evaluate_advancement(state.training_mode, self.session_metrics)
                    if unlocked:
                        advance_msg = f"UNLOCKED: {unlocked}"

            sys.stdout.write("\033[2J\033[H")
            print("=" * 68)
            print(" SESSION COMPLETE")
            print("=" * 68)
            sesh_acc = (session_correct / session_attempts * 100.0) if session_attempts > 0 else 0.0
            print(f" Session Accuracy: {sesh_acc:.1f}% ({session_correct}/{session_attempts})")
            
            total_att = sum(m.attempts for m in state.metrics.values())
            total_cor = sum(m.correct for m in state.metrics.values())
            overall_acc = (total_cor / total_att * 100.0) if total_att > 0 else 0.0
            print(f" Lifetime Accuracy: {overall_acc:.1f}%")
            print("-" * 68)
            input(" Press [Enter] to return to the Main Menu...")

        except KeyboardInterrupt:
            time.sleep(0.4)

    def profile_selection_menu(self) -> None:
        while True:
            sys.stdout.write("\033[2J\033[H")
            print("=" * 68)
            print("                 DIY MORSE TRAINER - v1.6")
            print("            Created by Christopher Webster (M7KQX)")
            print("                 https://www.m7kqx.co.uk")
            print("                      PROFILE SELECT")
            print("=" * 68)
            
            profiles = ProfileManager.list_profiles()
            if not profiles:
                print(" No profiles found.")
            else:
                for idx, p in enumerate(profiles, 1):
                    print(f" [{idx}] {p}")
            
            print("-" * 68)
            print(" [N] Create New Profile")
            if profiles:
                print(" [D] Delete a Profile")
            print(" [Q] Quit")
            print("=" * 68)

            choice = input("\nSelect Option > ").strip().upper()

            if choice == 'N':
                name = input("Enter new profile name (letters/numbers only): ").strip()
                if name.isalnum():
                    self.profile_mgr = ProfileManager(name)
                    return
                else:
                    print("Invalid name. Please use alphanumeric characters only.")
                    time.sleep(1.5)
            elif choice == 'D' and profiles:
                del_choice = input("Enter the number of the profile to DELETE: ").strip()
                if del_choice.isdigit() and 1 <= int(del_choice) <= len(profiles):
                    target = profiles[int(del_choice) - 1]
                    confirm = input(f"Are you sure you want to delete '{target}'? (Y/N): ").strip().upper()
                    if confirm == 'Y':
                        ProfileManager.delete_profile(target)
                        print(f"Profile '{target}' deleted.")
                        time.sleep(1)
            elif choice == 'Q':
                sys.exit(0)
            elif choice.isdigit() and 1 <= int(choice) <= len(profiles):
                self.profile_mgr = ProfileManager(profiles[int(choice) - 1])
                return

    def display_main_menu(self) -> None:
        sys.stdout.write("\033[2J\033[H")
        state = self.profile_mgr.state
        sl_str = str(state.session_length) if state.session_length > 0 else "Infinite"
        print("=" * 68)
        print("                 DIY MORSE TRAINER - v1.6")
        print("            Created by Christopher Webster (M7KQX)")
        print("                 https://www.m7kqx.co.uk")
        print(f"            Active Profile: {self.profile_mgr.profile_name}")
        print("=" * 68)
        print(f" [1] Koch Practice Set       (Level {state.koch_level} / {len(self.profile_mgr.get_active_pool('KOCH'))} characters active)")
        print(f" [2] 2-Letter Words          (Active Pool: {len(self.profile_mgr.get_active_pool('WORDS_2'))} words)")
        print(f" [3] 3-Letter Words          (Active Pool: {len(self.profile_mgr.get_active_pool('WORDS_3'))} words)")
        print(f" [4] 4-Letter Words          (Active Pool: {len(self.profile_mgr.get_active_pool('WORDS_4'))} words)")
        print(f" [5] Common Operator Names   (Active Pool: {len(self.profile_mgr.get_active_pool('NAMES'))} names)")
        print(f" [6] Core QSO Vocabulary     (Active Pool: {len(self.profile_mgr.get_active_pool('QSO'))} terms)")
        print(f" [7] Practice Weak Skills    (Top 10 lowest accuracy tokens)")
        print(f" [8] Head Copy Trainer       (Audio Recognition via K3NG Sidetone)")
        print("-" * 68)
        print(f" [S] Speed: {state.char_wpm}/{state.effective_wpm} WPM | [L] Session Length: {sl_str}")
        print(" [P] Switch/Manage Profiles")
        print(" [R] Reset Active Profile Progress")
        print(" [Q] Save & Exit")
        print("=" * 68)

    def main_loop(self) -> None:
        self.profile_selection_menu()

        if not self.init_serial():
            print("\033[91mError: Open CW Keyer serial port not detected.\033[0m")
            print("Verify USB connection and check permissions (`sudo usermod -a -G dialout $USER`).")
            time.sleep(2)

        while self.running:
            self.display_main_menu()
            choice = input("\nSelect Option > ").strip().upper()

            if choice in ["1", "2", "3", "4", "5", "6", "7", "8"]:
                mode_map = {
                    "1": "KOCH", "2": "WORDS_2", "3": "WORDS_3", 
                    "4": "WORDS_4", "5": "NAMES", "6": "QSO", 
                    "7": "WEAK", "8": "HEAD_COPY"
                }
                self.profile_mgr.state.training_mode = mode_map[choice]
                
                if choice == "8":
                    self.run_head_copy_session()
                else:
                    self.run_training_session()
                    
            elif choice == "L":
                try:
                    sl = int(input("Enter Challenges per Session (10, 25, 50, or 0 for Infinite): "))
                    self.profile_mgr.state.session_length = max(0, sl)
                    self.profile_mgr.save_profile()
                except ValueError:
                    pass
            elif choice == "S":
                try:
                    cw = int(input("Enter Character Speed (WPM) [15-35]: "))
                    ew = int(input("Enter Farnsworth Spacing (WPM) [5-30]: "))
                    self.profile_mgr.state.char_wpm = max(5, cw)
                    self.profile_mgr.state.effective_wpm = min(max(5, ew), cw)
                    self.profile_mgr.save_profile()
                except ValueError:
                    pass
            elif choice == "P":
                self.profile_mgr.save_profile()
                self.profile_selection_menu()
            elif choice == "R":
                confirm = input("\n\033[91mWARNING: This will delete all saved progress and metrics for this profile.\033[0m\nAre you sure? (Y/N) > ").strip().upper()
                if confirm == "Y":
                    self.profile_mgr.reset_profile()
                    print("\nProgress reset successfully.")
                    time.sleep(1.5)
            elif choice == "Q":
                self.profile_mgr.save_profile()
                if self.serial_conn and self.serial_conn.is_open:
                    self.serial_conn.close()
                sys.stdout.write("\033[2J\033[H")
                print(f"Session profile saved to ~/.morse_trainer/{self.profile_mgr.profile_name}_v1_6.json. 73!\n")
                self.running = False
                return


def main() -> None:
    app = MorseTrainerCLI()
    app.main_loop()


if __name__ == "__main__":
    main()
