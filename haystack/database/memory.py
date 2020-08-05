from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
from collections import defaultdict

from haystack.database.base import BaseDocumentStore, Document, Label
from haystack.indexing.utils import eval_data_from_file


class InMemoryDocumentStore(BaseDocumentStore):
    """
        In-memory document store
    """

    def __init__(self, embedding_field: Optional[str] = None):
        self.indexes: Dict[str, Dict] = defaultdict(dict)
        self.index: str = "document"
        self.label_index: str = "label"

    def write_documents(self, documents: Union[List[dict], List[Document]], index: Optional[str] = None):
        """
        Indexes documents for later queries.


       :param documents: a list of Python dictionaries or a list of Haystack Document objects.
                          For documents as dictionaries, the format is {"text": "<the-actual-text>"}.
                          Optionally: Include meta data via {"text": "<the-actual-text>",
                          "meta": {"name": "<some-document-name>, "author": "somebody", ...}}
                          It can be used for filtering and is accessible in the responses of the Finder.
        :param index: write documents to a custom namespace. For instance, documents for evaluation can be indexed in a
                      separate index than the documents for search.
        :return: None
        """
        index = index or self.index

        documents_objects = [Document.from_dict(d) if isinstance(d, dict) else d for d in documents]

        for document in documents_objects:
            self.indexes[index][document.id] = document

    def write_labels(self, labels: Union[List[dict], List[Label]], index: Optional[str] = None):
        index = index or self.label_index
        label_objects = [Label.from_dict(l) if isinstance(l, dict) else l for l in labels]

        for label in label_objects:
            label_id = str(uuid4())
            self.indexes[index][label_id] = label

    def get_document_by_id(self, id: str, index: Optional[str] = None) -> Document:
        index = index or self.index
        return self.indexes[index][id]

    def _convert_memory_hit_to_document(self, hit: Dict[str, Any], doc_id: Optional[str] = None) -> Document:
        document = Document(
            id=doc_id,
            text=hit.get("text", None),
            meta=hit.get("meta", {}),
            query_score=hit.get("query_score", None),
        )
        return document

    def query_by_embedding(self,
                           query_emb: List[float],
                           filters: Optional[Dict[str, List[str]]] = None,
                           top_k: int = 10,
                           index: Optional[str] = None) -> List[Document]:

        from numpy import dot
        from numpy.linalg import norm

        if filters:
            raise NotImplementedError("Setting `filters` is currently not supported in "
                                      "InMemoryDocumentStore.query_by_embedding(). Please remove filters or "
                                      "use a different DocumentStore (e.g. ElasticsearchDocumentStore).")

        index = index or self.index

        if query_emb is None:
            return []

        candidate_docs = []
        for idx, doc in self.indexes[index].items():
            doc.query_score = dot(query_emb, doc.embedding) / (
                norm(query_emb) * norm(doc.embedding)
            )
            candidate_docs.append(doc)

        return sorted(candidate_docs, key=lambda x: x.query_score, reverse=True)[0:top_k]

    def update_embeddings(self, retriever):
        """
        Updates the embeddings in the the document store using the encoding model specified in the retriever.
        This can be useful if want to add or change the embeddings for your documents (e.g. after changing the retriever config).

        :param retriever: Retriever
        :return: None
        """
        #TODO
        raise NotImplementedError("update_embeddings() is not yet implemented for this DocumentStore")

    def get_document_count(self, index: Optional[str] = None) -> int:
        index = index or self.index
        return len(self.indexes[index].items())

    def get_label_count(self, index: Optional[str] = None) -> int:
        index = index or self.label_index
        return len(self.indexes[index].items())

    def get_all_documents(self, index: Optional[str] = None, filters: Optional[Dict[str, List[str]]] = None) -> List[Document]:
        index = index or self.index
        documents = list(self.indexes[index].values())
        filtered_documents = []

        if filters:
            for doc in documents:
                is_hit = True
                for key, values in filters.items():
                    if doc.meta.get(key):
                        if doc.meta[key] not in values:
                            is_hit = False
                    else:
                        is_hit = False
                if is_hit:
                    filtered_documents.append(doc)
        else:
            filtered_documents = documents

        return filtered_documents

    def get_all_labels(self, index: str = None, filters: Optional[Dict[str, List[str]]] = None) -> List[Label]:
        index = index or self.label_index

        if filters:
            result = []
            for label in self.indexes[index].values():
                label_dict = label.to_dict()
                is_hit = True
                for key, values in filters.items():
                    if label_dict[key] not in values:
                        is_hit = False
                        break
                if is_hit:
                    result.append(label)
        else:
            result = list(self.indexes[index].values())

        return result

    def add_eval_data(self, filename: str, doc_index: Optional[str] = None, label_index: Optional[str] = None):
        """
        Adds a SQuAD-formatted file to the DocumentStore in order to be able to perform evaluation on it.

        :param filename: Name of the file containing evaluation data
        :type filename: str
        :param doc_index: Elasticsearch index where evaluation documents should be stored
        :type doc_index: str
        :param label_index: Elasticsearch index where labeled questions should be stored
        :type label_index: str
        """

        docs, labels = eval_data_from_file(filename)
        doc_index = doc_index or self.index
        label_index = label_index or self.label_index
        self.write_documents(docs, index=doc_index)
        self.write_labels(labels, index=label_index)

    def delete_all_documents(self, index: Optional[str] = None):
        """
        Delete all documents in a index.

        :param index: index name
        :return: None
        """

        index = index or self.index
        self.indexes[index] = {}
