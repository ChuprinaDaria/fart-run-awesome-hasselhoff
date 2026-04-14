//! sentinel — fart.run cross-platform host IDS
//!
//! Because your vibe-coded app shouldn't have a cryptominer running next to it.

mod processes;
mod network;
mod filesystem;
mod crontab;
mod secrets;
mod autostart;

use pyo3::prelude::*;

/// sentinel Python module — cross-platform security scanning at native speed.
///
/// Because your vibe-coded app shouldn't have a cryptominer in crontab.
#[pymodule]
fn sentinel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<processes::ProcessFinding>()?;
    m.add_function(wrap_pyfunction!(processes::scan_processes, m)?)?;
    m.add_class::<network::NetworkFinding>()?;
    m.add_function(wrap_pyfunction!(network::scan_network, m)?)?;
    m.add_class::<filesystem::FileFinding>()?;
    m.add_function(wrap_pyfunction!(filesystem::scan_filesystem, m)?)?;
    m.add_class::<crontab::CronFinding>()?;
    m.add_function(wrap_pyfunction!(crontab::scan_scheduled_tasks, m)?)?;
    m.add_class::<secrets::SecretFinding>()?;
    m.add_function(wrap_pyfunction!(secrets::scan_secrets, m)?)?;
    m.add_class::<autostart::AutostartFinding>()?;
    m.add_function(wrap_pyfunction!(autostart::scan_autostart, m)?)?;
    Ok(())
}
