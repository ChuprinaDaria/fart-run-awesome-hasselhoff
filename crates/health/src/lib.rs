//! health — project health scanner for vibe coders.

mod common;
mod entry_points;
mod file_tree;
mod module_map;
mod monsters;

use pyo3::prelude::*;

#[pymodule]
fn health(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<file_tree::FileTreeResult>()?;
    m.add_function(wrap_pyfunction!(file_tree::scan_file_tree, m)?)?;

    m.add_class::<entry_points::EntryPoint>()?;
    m.add_class::<entry_points::EntryPointsResult>()?;
    m.add_function(wrap_pyfunction!(entry_points::scan_entry_points, m)?)?;

    m.add_class::<monsters::MonsterFile>()?;
    m.add_class::<monsters::MonstersResult>()?;
    m.add_function(wrap_pyfunction!(monsters::scan_monsters, m)?)?;

    m.add_class::<module_map::ModuleInfo>()?;
    m.add_class::<module_map::ModuleMapResult>()?;
    m.add_function(wrap_pyfunction!(module_map::scan_module_map, m)?)?;

    Ok(())
}
