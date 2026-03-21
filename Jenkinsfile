pipeline {
  agent any

  environment {
    REPO = "sniper-bot-nightly"
    TAG  = "${env.BUILD_NUMBER}"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Safety Check') {
      steps {
        sh '''
          docker -v
          python3 --version
        '''
      }
    }

    stage('Run Unit Tests') {
      steps {
        sh '''
          python3 -m venv venv
          . venv/bin/activate
          pip install -U pip setuptools wheel
          pip install ".[test]"
          cd tests
          pytest -m unit 
        '''
      }
    }

    stage('Build Image') {
      steps {
        sh 'docker build -f Dockerfile -t $REPO:$TAG .'
      }
    }

    stage('Push Image to Docker Hub') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'DH_USER', passwordVariable: 'DH_PASS')]) {
          sh '''
            REMOTE_IMAGE="$DH_USER/$REPO:$TAG"
            echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
            docker tag $REPO:$TAG "$REMOTE_IMAGE"
            docker push "$REMOTE_IMAGE"
          '''
        }
      }
    }

    stage('Pull & Validate') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'DH_USER', passwordVariable: 'DH_PASS')]) {
          sh '''
            REMOTE_IMAGE="$DH_USER/$REPO:$TAG"
            docker pull "$REMOTE_IMAGE"
            docker run --rm "$REMOTE_IMAGE" python -c "import services.scam_checker; import services.liquidity_analyzer; print('image ok')"
          '''
        }
      }
    }
  }

  post {
    always {
      sh '''
        docker logout || true
      '''
    }
  }
}