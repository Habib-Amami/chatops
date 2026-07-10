# Intégration EC2 (lecture seule) — LocalStack

## Résumé

Ajout de la capacité pour l'agent ChatOps de **lister les instances EC2** (machines virtuelles AWS) via LocalStack, en lecture seule. Suit le même pattern à trois couches déjà utilisé pour Kubernetes (`client` → `service` → `tool`).

L'agent peut désormais répondre à des questions comme :
> *"Quelles sont les instances EC2 actives ?"*

## Architecture

```
Agent (LLM)
    │
    ▼
agent/tools/aws/ec2_tools.py          # Exposition du tool au LLM
    │
    ▼
platforms/aws/services/ec2_service.py # Logique métier (lecture, formatage)
    │
    ▼
platforms/aws/client.py               # Connexion (AWSClientFactory)
    │
    ▼
LocalStack (localhost:4566)           # Simulateur AWS local
```

Cette séparation garde chaque couche responsable d'une seule chose :
- **`client.py`** — comment se connecter (LocalStack ou AWS réel selon `Settings.aws_target`)
- **`ec2_service.py`** — quoi faire (interroger EC2, nettoyer/structurer la réponse)
- **`ec2_tools.py`** — comment le présenter au LLM (docstring, décorateur `@tool`)

## Fichiers ajoutés

| Fichier | Contenu |
|---|---|
| `app/platforms/aws/services/ec2_service.py` | `EC2Service` + modèle `EC2InstanceSummary` |
| `app/platforms/aws/services/__init__.py` | Export de `EC2Service` |
| `app/agent/tools/aws/ec2_tools.py` | `create_ec2_tools()` — tool `list_ec2_instances` |
| `app/agent/tools/aws/__init__.py` | Export de `create_ec2_tools` |
| `tests/test_ec2_service.py` | Tests d'intégration contre LocalStack *(en cours de finalisation)* |

**Fichiers existants réutilisés sans modification** : `app/platforms/aws/client.py` (`AWSClientFactory`), `app/core/config.py` (`Settings.aws_*`).

## Fonctionnalité

### `EC2Service.list_instances(state_filter=None)`

Retourne une liste de `EC2InstanceSummary` (id, type, état, IP privée/publique, date de lancement), en filtrant optionnellement par état (`"running"`, `"stopped"`, `"terminated"`).

### `list_ec2_instances` (tool agent)

Wrapper LangChain exposant `list_instances()` au LLM. La docstring guide l'agent sur quand l'utiliser (questions sur des instances, serveurs, machines virtuelles).

## Prérequis pour exécuter/tester

1. **Docker Desktop** démarré
2. **LocalStack** actif (via LocalStack Desktop ou `docker run`), service EC2 disponible
3. Dépendances installées :
   ```powershell
   uv add boto3 awscli awscli-local
   ```

## Configuration (déjà en place dans `.env` / `Settings`)

| Variable | Valeur par défaut | Rôle |
|---|---|---|
| `AWS_TARGET` | `localstack` | Bascule LocalStack / AWS réel |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | Adresse de LocalStack |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `test` / `test` | Credentials factices acceptés par LocalStack |
| `ALLOW_REAL_AWS` | `false` | Garde-fou empêchant un accès AWS réel accidentel |

## Comment tester manuellement

```powershell
# 1. Créer une instance factice dans LocalStack
uv run awslocal ec2 run-instances --image-id ami-12345678 --instance-type t2.micro --count 1

# 2. Vérifier qu'elle existe
uv run awslocal ec2 describe-instances

# 3. Vérifier que le service Python la récupère (script ponctuel, non commité)
uv run python scratch_test_ec2.py
```

## Statut

| Élément | Statut |
|---|---|
| Lecture des instances EC2 | ✅ Fait, validé contre LocalStack |
| Filtrage par état | ✅ Fait |
| Exposition au LLM (tool) | ✅ Fait |
| Câblage dans `api/dependencies.py` | ⏳ À faire |
| Enregistrement du tool dans l'agent | ⏳ À faire |
| Test automatisé finalisé | ⏳ En cours (fixture de setup/teardown à trancher) |
| Actions d'écriture (start/stop/terminate) | ❌ Hors périmètre — prévu à l'étape "Sécurité et confirmation" |
