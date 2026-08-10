terraform {
  backend "s3" {
    bucket  = "emr-demo-state-zxcvzxcv23"
    key     = "synth-canary-template/terraform.tfstate" # <- change to <project>/terraform.tfstate
    region  = "us-east-2"
    encrypt = true
  }
}
