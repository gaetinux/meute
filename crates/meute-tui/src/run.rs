//! Terminal loop.

use std::time::Duration;

use ratatui::crossterm::event::{self, Event, KeyCode, KeyEventKind, KeyModifiers};

use crate::board::{Board, BoardBackend, BoardData};

const TICK: Duration = Duration::from_millis(250);

/// Run the dashboard until the user quits (Ctrl+C).
///
/// The terminal is restored on every exit path, including errors.
///
/// # Errors
/// Terminal input/output errors.
pub fn run_board(backend: &mut dyn BoardBackend) -> std::io::Result<()> {
    let mut terminal = ratatui::init();
    let result = event_loop(&mut terminal, backend);
    ratatui::restore();
    result
}

fn event_loop(
    terminal: &mut ratatui::DefaultTerminal,
    backend: &mut dyn BoardBackend,
) -> std::io::Result<()> {
    let mut board = Board::new(BoardData::default());
    loop {
        match backend.load() {
            Ok(Some(data)) => board.set_data(data),
            Ok(None) => {}
            Err(message) => board.set_error(message),
        }
        terminal.draw(|frame| board.render(frame))?;
        if !event::poll(TICK)? {
            continue;
        }
        if let Event::Key(key) = event::read()? {
            let ctrl_c =
                key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL);
            if key.kind == KeyEventKind::Press && ctrl_c {
                return Ok(());
            }
            if let Some(action) = board.on_key(key) {
                if let Err(message) = backend.perform(action) {
                    board.set_error(message);
                }
            }
        }
    }
}
