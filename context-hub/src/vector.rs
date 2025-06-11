use anyhow::Result;
use fastembed::{InitOptions, TextEmbedding};
use hnsw_rs::prelude::*;
use std::collections::HashMap;
use uuid::Uuid;

pub struct VectorIndex {
    model: TextEmbedding,
    index: Hnsw<f32, DistCosine>,
    mapping: HashMap<PointId, Uuid>,
    next: PointId,
}

impl VectorIndex {
    pub fn new() -> Result<Self> {
        let model = TextEmbedding::try_new(InitOptions::default())?;
        // default dimension for the default model is 384
        let index = Hnsw::<f32, DistCosine>::new(16, 100_000, 16, 200, DistCosine {});
        Ok(Self { model, index, mapping: HashMap::new(), next: 0 })
    }

    pub fn index_document(&mut self, id: Uuid, text: &str) -> Result<()> {
        let vec = self.model.embed(vec![text.to_string()], None)?.remove(0);
        let pid = self.next;
        self.next += 1;
        self.index.insert((vec.as_slice(), pid));
        self.mapping.insert(pid, id);
        Ok(())
    }

    pub fn search(&self, query: &str, k: usize) -> Result<Vec<Uuid>> {
        let vec = self.model.embed(vec![query.to_string()], None)?.remove(0);
        let res = self.index.search(&vec, k, 200);
        Ok(res
            .into_iter()
            .filter_map(|n| self.mapping.get(&n.d_id).copied())
            .collect())
    }
}
