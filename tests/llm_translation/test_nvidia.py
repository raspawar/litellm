import json
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock

sys.path.insert(
    0, os.path.abspath("../..")
)  # Adds the parent directory to the system path


import httpx
import pytest
import respx
from respx import MockRouter

import os
from contextlib import contextmanager
from typing import Generator
import litellm
from litellm import Choices, Message, ModelResponse, EmbeddingResponse, Usage
from litellm import completion

@contextmanager
def no_env_var(var: str) -> Generator[None, None, None]:
    try:
        if val := os.environ.get(var, None):
            del os.environ[var]
        yield
    finally:
        if val:
            os.environ[var] = val
        else:
            if var in os.environ:
                del os.environ[var]


## mock /models endpoint
@pytest.fixture
def mock_models_endpoint():
    response_data = {
        "object": "list",
        "data": [
            {
                "id": "nv-mistralai/mistral-nemo-12b-instruct",
                "object": "model",
                "created": 735790403,
                "owned_by": "01-ai"
            },
            {
                "id": "nvidia/vila",
                "object": "model",
                "created": 735790403,
                "owned_by": "abacusai"
            },
    ]
    }
    with respx.mock(base_url="https://integrate.api.nvidia.com/v1") as mock:
        mock.get("/models").respond(200, json=response_data)
        yield mock


def test_completion_missing_key():
    with no_env_var("NVIDIA_API_KEY"):
        with pytest.raises(litellm.exceptions.AuthenticationError):
            completion(
                model="nvidia/databricks/dbrx-instruct",
                messages=[
                    {
                        "role": "user",
                        "content": "What's the weather like in Boston today in Fahrenheit?",
                    }
                ],
                presence_penalty=0.5,
                frequency_penalty=0.1,
            )

def test_completion_bogus_key():
    with pytest.raises(litellm.exceptions.AuthenticationError):
        completion(
            api_key="bogus-key",
            model="nvidia/databricks/dbrx-instruct",
            messages=[
                {
                    "role": "user",
                    "content": "What's the weather like in Boston today in Fahrenheit?",
                }
            ],
            presence_penalty=0.5,
            frequency_penalty=0.1,
        )

@pytest.mark.skipif("NVIDIA_API_KEY" not in os.environ, reason="NVIDIA_API_KEY environment variable is not set.")
def test_completion_invalid_model():
    with pytest.raises(litellm.exceptions.BadRequestError) as err_msg:
        completion(
            model="invalid_model",
            messages=[
                {
                    "role": "user",
                    "content": "What's the weather like in Boston today in Fahrenheit?",
                }
            ],
            presence_penalty=0.5,
            frequency_penalty=0.1,
        )
    assert "LLM Provider NOT provided. Pass in the LLM provider you are trying to call. You passed model=invalid_model" in str(err_msg.value)


@pytest.mark.respx
def test_completion_nvidia(respx_mock: MockRouter):
    litellm.set_verbose = True
    mock_response = ModelResponse(
        id="cmpl-mock",
        choices=[Choices(message=Message(content="Mocked response", role="assistant"))],
        created=int(datetime.now().timestamp()),
        model="databricks/dbrx-instruct",
    )
    model_name = "nvidia/databricks/dbrx-instruct"

    mock_request = respx_mock.post(
        "https://integrate.api.nvidia.com/v1/chat/completions"
    ).mock(return_value=httpx.Response(200, json=mock_response.dict()))
    try:
        response = completion(
            api_key="bogus-key",
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": "What's the weather like in Boston today in Fahrenheit?",
                }
            ],
            presence_penalty=0.5,
            frequency_penalty=0.1,
        )
        # Add any assertions here to check the response
        print(response)
        assert response.choices[0].message.content is not None
        assert len(response.choices[0].message.content) > 0

        assert mock_request.called
        request_body = json.loads(mock_request.calls[0].request.content)

        print("request_body: ", request_body)

        assert request_body == {
            "messages": [
                {
                    "role": "user",
                    "content": "What's the weather like in Boston today in Fahrenheit?",
                }
            ],
            "model": "databricks/dbrx-instruct",
            "frequency_penalty": 0.1,
            "presence_penalty": 0.5,
        }
    except litellm.exceptions.Timeout as e:
        pass
    except Exception as e:
        pytest.fail(f"Error occurred: {e}")


@pytest.mark.respx
def test_embedding_nvidia(respx_mock: MockRouter):
    litellm.set_verbose = True
    mock_response = EmbeddingResponse(
        model="nvidia/databricks/dbrx-instruct",
        data=[
            {
                "embedding": [0.1, 0.2, 0.3],
                "index": 0,
            }
        ],
        usage=Usage(
            prompt_tokens=10,
            completion_tokens=0,
            total_tokens=10,
        ),
    )
    mock_request = respx_mock.post(
        "https://integrate.api.nvidia.com/v1/embeddings"
    ).mock(return_value=httpx.Response(200, json=mock_response.dict()))
    response = litellm.embedding(
        api_key="bogus-key",
        model="nvidia/nvidia/nv-embedqa-e5-v5",
        input="What is the meaning of life?",
        input_type="passage",
    )
    assert mock_request.called
    request_body = json.loads(mock_request.calls[0].request.content)
    print("request_body: ", request_body)
    assert request_body == {
        "input": "What is the meaning of life?",
        "model": "nvidia/nv-embedqa-e5-v5",
        "input_type": "passage",
    }
